import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class DraftProfile:
    name: str
    template_dir: str
    content_file: str
    content_mirrors: tuple[str, ...] = ()
    timeline_content_file: Optional[str] = None
    is_capcut_env: bool = True
    platform: Optional[Dict[str, object]] = None


CAPCUT_PLATFORM = {
    "app_id": 359289,
    "app_source": "cc",
    "app_version": "6.5.0",
    "device_id": "c4ca4238a0b923820dcc509a6f75849b",
    "hard_disk_id": "307563e0192a94465c0e927fbc482942",
    "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
    "os": "mac",
    "os_version": "15.5",
}

JIANYING_10_PLATFORM = {
    "app_id": 3704,
    "app_source": "lv",
    "app_version": "10.2.0",
    "os": "windows",
}

PROFILES: Dict[str, DraftProfile] = {
    "capcut_legacy": DraftProfile(
        name="capcut_legacy",
        template_dir="template",
        content_file="draft_info.json",
        # CapCut keeps these as copies of draft_info.json; the template's are stale
        content_mirrors=("draft_info.json.bak", "template-2.tmp"),
        is_capcut_env=True,
        platform=CAPCUT_PLATFORM,
    ),
    "jianying_legacy": DraftProfile(
        name="jianying_legacy",
        template_dir="template_jianying",
        content_file="draft_info.json",
        is_capcut_env=False,
        platform=JIANYING_10_PLATFORM,
    ),
    "jianying_pro_10": DraftProfile(
        name="jianying_pro_10",
        template_dir="template_jianying_10_2",
        content_file="draft_content.json",
        content_mirrors=("draft_content.json.bak", "template-2.tmp"),
        timeline_content_file="template.tmp",
        is_capcut_env=False,
        platform=JIANYING_10_PLATFORM,
    ),
}

PROFILE_ALIASES = {
    "capcut": "jianying_pro_10",
    "capcut_legacy": "capcut_legacy",
    "capcut_modern": "jianying_pro_10",
    "jianying": "jianying_pro_10",
    "jianying_legacy": "jianying_legacy",
    "jianying_10": "jianying_pro_10",
    "jianying_10_x": "jianying_pro_10",
    "jianying_pro_10": "jianying_pro_10",
    "jianying_pro_10_2": "jianying_pro_10",
    "jianying_pro_10_2_0": "jianying_pro_10",
}


def normalize_profile_name(name: Optional[str]) -> str:
    if not name:
        return "jianying_pro_10"
    key = name.strip().lower().replace(".", "_").replace("-", "_")
    if key not in PROFILE_ALIASES:
        raise ValueError(
            f"Unknown draft profile '{name}'. Supported profiles: {', '.join(sorted(PROFILE_ALIASES))}"
        )
    return PROFILE_ALIASES[key]


def get_draft_profile(name: Optional[str] = None) -> DraftProfile:
    if name is None:
        try:
            from settings.local import DRAFT_PROFILE
        except Exception:
            DRAFT_PROFILE = "jianying_pro_10"
        name = DRAFT_PROFILE
    return PROFILES[normalize_profile_name(name)]


def get_template_dir(name: Optional[str] = None) -> str:
    return get_draft_profile(name).template_dir


def new_draft_id() -> str:
    """Return a fresh ID in CapCut's format (uppercase UUID)."""
    return str(uuid.uuid4()).upper()


def _update_json_file(path: Path, updates: Dict[str, object], only_existing: bool = False) -> bool:
    """Set top-level keys in a JSON file; skip files that are missing or not a JSON object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    if only_existing:
        updates = {key: value for key, value in updates.items() if key in data}
        if not updates:
            return False
    data.update(updates)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return True


def set_draft_meta_location(draft_dir: os.PathLike) -> None:
    """Point draft_meta_info.json's name and paths at the folder it now lives in."""
    draft_path = Path(draft_dir).resolve()
    _update_json_file(draft_path / "draft_meta_info.json", {
        "draft_name": draft_path.name,
        "draft_fold_path": str(draft_path),
        "draft_root_path": str(draft_path.parent),
    })


def assign_new_draft_ids(draft_dir: os.PathLike) -> Dict[str, str]:
    """Give a folder freshly copied from a template its own project and template.tmp IDs.

    Template folders ship with fixed IDs, so without this every new draft would share
    them. Only call this on a new draft folder, never on an existing CapCut project.
    """
    draft_path = Path(draft_dir)
    ids = {"draft_id": new_draft_id(), "template_tmp_id": new_draft_id()}
    _update_json_file(draft_path / "draft_meta_info.json", {"draft_id": ids["draft_id"]})
    _update_json_file(draft_path / "template.tmp", {"id": ids["template_tmp_id"]}, only_existing=True)
    set_draft_meta_location(draft_path)
    return ids


DRAFT_JSON_SUFFIXES = (".json", ".tmp", ".bak")


def _under_dir(value: str, root: str) -> Optional[str]:
    """Return value's path relative to root if value is a path inside root, else None."""
    norm_value = os.path.normcase(os.path.normpath(value))
    norm_root = os.path.normcase(os.path.normpath(root))
    if norm_value.startswith(norm_root + os.sep):
        return os.path.relpath(os.path.normpath(value), os.path.normpath(root))
    return None


def relocate_draft_paths(draft_dir: os.PathLike, old_root: os.PathLike, new_root: os.PathLike) -> List[Path]:
    """Rewrite paths under old_root to the same place under new_root in every JSON file of draft_dir.

    A deployed copy of a draft still references media in the folder it was built in;
    CapCut can't resolve those, so they must point into the deployed project instead.
    Returns the files that changed. Only draft_dir is written.
    """
    old_root, new_root = os.path.abspath(old_root), os.path.abspath(new_root)

    def rewrite(node):
        if isinstance(node, dict):
            return {key: rewrite(value) for key, value in node.items()}
        if isinstance(node, list):
            return [rewrite(value) for value in node]
        if isinstance(node, str):
            relative = _under_dir(node, old_root)
            if relative is not None:
                return os.path.join(new_root, relative)
        return node

    changed: List[Path] = []
    for path in sorted(Path(draft_dir).rglob("*")):
        if not path.is_file() or not path.name.endswith(DRAFT_JSON_SUFFIXES):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        new_data = rewrite(data)
        if new_data != data:
            path.write_text(json.dumps(new_data, ensure_ascii=False), encoding="utf-8")
            changed.append(path)
    return changed


def _is_url(value: str) -> bool:
    return "://" in value


def localize_material_sources(draft_dir: os.PathLike) -> List[Path]:
    """Point local-file remote_url values at the material's own path in every JSON file of draft_dir.

    remote_url records where media was fetched from. For a local source that is a path
    outside the project, so a deployed draft would still point back at it. Real URLs are kept.
    """
    changed: List[Path] = []
    for path in sorted(Path(draft_dir).rglob("*")):
        if not path.is_file() or not path.name.endswith(DRAFT_JSON_SUFFIXES):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        materials = data.get("materials") if isinstance(data, dict) else None
        if not isinstance(materials, dict):
            continue
        updated = False
        for kind in ("videos", "audios"):
            for material in materials.get(kind) or []:
                source, media_path = material.get("remote_url"), material.get("path")
                if source and media_path and not _is_url(source) and source != media_path:
                    material["remote_url"] = media_path
                    updated = True
        if updated:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            changed.append(path)
    return changed


def find_draft_paths(draft_dir: os.PathLike, root: os.PathLike) -> List[str]:
    """List 'file: value' for every string in draft_dir's JSON files that is a path inside root."""
    root = os.path.abspath(root)
    found: List[str] = []

    def walk(node, path):
        if isinstance(node, dict):
            for value in node.values():
                walk(value, path)
        elif isinstance(node, list):
            for value in node:
                walk(value, path)
        elif isinstance(node, str) and _under_dir(node, root) is not None:
            found.append(f"{path}: {node}")

    for path in sorted(Path(draft_dir).rglob("*")):
        if path.is_file() and path.name.endswith(DRAFT_JSON_SUFFIXES):
            try:
                walk(json.loads(path.read_text(encoding="utf-8-sig")), path)
            except (OSError, ValueError):
                continue
    return found


def resolve_main_timeline_dir(draft_dir: os.PathLike) -> Optional[Path]:
    """Return Timelines/<main_timeline_id> from Timelines/project.json, or None.

    Without a usable project.json, only a single timeline folder is trusted.
    """
    timelines_dir = Path(draft_dir) / "Timelines"
    if not timelines_dir.is_dir():
        return None
    try:
        project = json.loads((timelines_dir / "project.json").read_text(encoding="utf-8-sig"))
        main_id = project.get("main_timeline_id")
    except (OSError, ValueError, AttributeError):
        main_id = None
    if main_id and (timelines_dir / main_id).is_dir():
        return timelines_dir / main_id
    timeline_dirs = [path for path in timelines_dir.iterdir() if path.is_dir()]
    return timeline_dirs[0] if len(timeline_dirs) == 1 else None


def write_profile_content(profile: DraftProfile, draft_dir: os.PathLike, content: str) -> List[Path]:
    draft_path = Path(draft_dir)
    written: List[Path] = []
    content_data = json.loads(content)

    # Auto-adjust canvas_config ratio based on dimensions
    canvas_cfg = content_data.get("canvas_config", {})
    w = canvas_cfg.get("width", content_data.get("width", 1080))
    h = canvas_cfg.get("height", content_data.get("height", 1920))
    if canvas_cfg.get("ratio") in ("original", None, ""):
        if h > w:
            canvas_cfg["ratio"] = "9:16"
        elif w > h:
            canvas_cfg["ratio"] = "16:9"
        elif w == h:
            canvas_cfg["ratio"] = "1:1"
    content_data["canvas_config"] = canvas_cfg
    content = json.dumps(content_data, ensure_ascii=False, indent=2)

    # Remove any stale .locked files in draft directory
    try:
        lock_file = draft_path / ".locked"
        if lock_file.exists():
            lock_file.unlink()
    except Exception:
        pass

    targets = [profile.content_file, *profile.content_mirrors]
    for relative_path in targets:
        path = draft_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    timelines_dir = draft_path / "Timelines"
    if timelines_dir.is_dir():
        timeline_dir = resolve_main_timeline_dir(draft_path)
        timeline_id = content_data.get("id")
        retargeted = False
        if timeline_dir is not None and timeline_id and timeline_dir.name != timeline_id:
            desired_timeline_dir = timelines_dir / timeline_id
            if desired_timeline_dir.exists():
                shutil.rmtree(desired_timeline_dir)
            timeline_dir.rename(desired_timeline_dir)
            timeline_dir = desired_timeline_dir
            retargeted = True

        if timeline_dir is not None:
            timeline_targets = set(targets)
            if profile.timeline_content_file:
                timeline_targets.add(profile.timeline_content_file)
            for relative_path in timeline_targets:
                path = timeline_dir / relative_path
                path.write_text(content, encoding="utf-8")
                written.append(path)

        # Keep a project.json written by CapCut unless the main timeline changed
        project_missing = not (timelines_dir / "project.json").exists()
        if timeline_id and (retargeted or project_missing):
            now_us = int(time.time() * 1_000_000)
            project = {
                "config": {
                    "color_space": -1,
                    "render_index_track_mode_on": False,
                    "use_float_render": False,
                },
                "create_time": now_us,
                "id": timeline_id,
                "main_timeline_id": timeline_id,
                "timelines": [
                    {
                        "create_time": now_us,
                        "id": timeline_id,
                        "is_marked_delete": False,
                        "name": "时间线01",
                        "update_time": now_us,
                    }
                ],
                "update_time": now_us,
                "version": 0,
            }
            for relative_path in ("project.json", "project.json.bak"):
                path = timelines_dir / relative_path
                path.write_text(json.dumps(project, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                written.append(path)

            layout_path = draft_path / "timeline_layout.json"
            if layout_path.exists():
                layout = json.loads(layout_path.read_text(encoding="utf-8"))
                for item in layout.get("dockItems", []):
                    item["timelineIds"] = [timeline_id]
                    item["timelineNames"] = ["时间线01"]
                layout_path.write_text(json.dumps(layout, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                written.append(layout_path)

    return written
