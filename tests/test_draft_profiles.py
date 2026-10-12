import json
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest


def test_jianying_10_profile_uses_versioned_template_and_content_names():
    from draft_profiles import get_draft_profile

    profile = get_draft_profile("jianying_pro_10")

    assert profile.name == "jianying_pro_10"
    assert profile.template_dir == "template_jianying_10_2"
    assert profile.content_file == "draft_content.json"
    assert "template-2.tmp" in profile.content_mirrors
    assert profile.is_capcut_env is False


def test_legacy_profiles_keep_existing_template_names():
    from draft_profiles import get_draft_profile

    capcut = get_draft_profile("capcut_legacy")
    jianying = get_draft_profile("jianying_legacy")

    assert capcut.template_dir == "template"
    assert capcut.content_file == "draft_info.json"
    assert capcut.is_capcut_env is True
    assert jianying.template_dir == "template_jianying"
    assert jianying.content_file == "draft_info.json"
    assert jianying.is_capcut_env is False


def test_write_profile_content_updates_main_mirrors_and_timeline(tmp_path):
    from draft_profiles import get_draft_profile, write_profile_content

    draft_dir = tmp_path / "draft"
    timeline_dir = draft_dir / "Timelines" / "timeline-1"
    timeline_dir.mkdir(parents=True)
    (draft_dir / "timeline_layout.json").write_text(
        json.dumps({"dockItems": [{"timelineIds": ["timeline-1"], "timelineNames": ["Timeline 1"]}]}),
        encoding="utf-8",
    )

    payload = {"id": "timeline-fixed", "tracks": [], "materials": {}, "duration": 0}
    profile = get_draft_profile("jianying_pro_10")

    written = write_profile_content(profile, draft_dir, json.dumps(payload, ensure_ascii=False))

    renamed_timeline_dir = draft_dir / "Timelines" / "timeline-fixed"
    expected = {
        draft_dir / "draft_content.json",
        draft_dir / "template-2.tmp",
        renamed_timeline_dir / "draft_content.json",
        renamed_timeline_dir / "template-2.tmp",
        renamed_timeline_dir / "template.tmp",
    }
    assert expected.issubset(set(written))
    for path in expected:
        assert json.loads(path.read_text(encoding="utf-8")) == payload
    project = json.loads((draft_dir / "Timelines" / "project.json").read_text(encoding="utf-8"))
    layout = json.loads((draft_dir / "timeline_layout.json").read_text(encoding="utf-8"))
    assert project["main_timeline_id"] == "timeline-fixed"
    assert layout["dockItems"][0]["timelineIds"] == ["timeline-fixed"]


def test_script_dumps_uses_requested_profile_platform_and_mask_key():
    import pyJianYingDraft as draft
    from draft_profiles import get_draft_profile

    profile = get_draft_profile("jianying_pro_10")
    script = draft.Script_file(1080, 1920)

    payload = json.loads(script.dumps(profile))

    assert payload["platform"] == profile.platform
    assert payload["last_modified_platform"] == profile.platform
    assert "masks" in payload["materials"]
    assert "common_mask" not in payload["materials"]


def test_windows_draft_asset_path_keeps_drive_root():
    from save_draft_impl import build_asset_path

    path = build_asset_path(
        r"D:\JianyingPro Drafts",
        "draft-1",
        "video",
        "clip.mp4",
    )

    assert path == r"D:\JianyingPro Drafts\draft-1\assets\video\clip.mp4"


def test_shared_draft_asset_path_keeps_drive_root():
    from util import build_draft_asset_path

    assert build_draft_asset_path(
        r"D:\JianyingPro Drafts",
        "draft-1",
        "image",
        "cover.png",
    ) == r"D:\JianyingPro Drafts\draft-1\assets\image\cover.png"


def test_save_draft_writes_to_requested_draft_folder(tmp_path, monkeypatch):
    import save_draft_impl
    from draft_cache import DRAFT_CACHE
    from draft_profiles import get_draft_profile
    from save_task_cache import create_task

    draft_id = "draft-target-folder"
    payload = {"tracks": [], "materials": {}, "duration": 0}
    project_draft_dir = Path(save_draft_impl.__file__).resolve().parent / draft_id
    if project_draft_dir.exists():
        shutil.rmtree(project_draft_dir)

    script = SimpleNamespace(
        materials=SimpleNamespace(audios=[], videos=[]),
        tracks={},
        dumps=lambda profile=None: json.dumps(payload),
    )
    DRAFT_CACHE[draft_id] = script
    create_task(draft_id)

    monkeypatch.setattr(save_draft_impl, "get_draft_profile", lambda: get_draft_profile("jianying_pro_10"))
    monkeypatch.setattr(save_draft_impl, "update_media_metadata", lambda script, task_id=None: None)
    monkeypatch.setattr(save_draft_impl, "IS_UPLOAD_DRAFT", False)

    # auto_deploy=False keeps the test out of the real CapCut projects folder
    save_draft_impl.save_draft_background(draft_id, str(tmp_path), draft_id, auto_deploy=False)

    assert (tmp_path / draft_id / "draft_content.json").exists()
    assert (tmp_path / draft_id / "Timelines").exists()
    assert not project_draft_dir.exists()


def _make_timelines(draft_dir, timeline_ids, main_id=None):
    for timeline_id in timeline_ids:
        (draft_dir / "Timelines" / timeline_id).mkdir(parents=True)
    if main_id:
        (draft_dir / "Timelines" / "project.json").write_text(
            json.dumps({"main_timeline_id": main_id, "config": {"hdr_vivid": False}}), encoding="utf-8"
        )


def test_resolve_main_timeline_dir_uses_project_json(tmp_path):
    from draft_profiles import resolve_main_timeline_dir

    _make_timelines(tmp_path, ["aaa", "bbb"], main_id="bbb")

    assert resolve_main_timeline_dir(tmp_path) == tmp_path / "Timelines" / "bbb"


def test_resolve_main_timeline_dir_refuses_to_guess(tmp_path):
    from draft_profiles import resolve_main_timeline_dir

    assert resolve_main_timeline_dir(tmp_path) is None
    _make_timelines(tmp_path, ["aaa", "bbb"])
    assert resolve_main_timeline_dir(tmp_path) is None


def test_capcut_profile_writes_draft_info_into_main_timeline(tmp_path):
    from draft_profiles import get_draft_profile, write_profile_content

    _make_timelines(tmp_path, ["other", "main"], main_id="main")
    project_before = (tmp_path / "Timelines" / "project.json").read_bytes()
    payload = {"id": "main", "tracks": [{"type": "video"}], "materials": {}, "duration": 1}

    write_profile_content(get_draft_profile("capcut_legacy"), tmp_path, json.dumps(payload))

    for path in (tmp_path / "draft_info.json", tmp_path / "Timelines" / "main" / "draft_info.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["tracks"] == payload["tracks"]
    assert not any((tmp_path / "Timelines" / "other").iterdir())
    assert not (tmp_path / "draft_content.json").exists()
    # CapCut's own project.json is left alone when the main timeline is unchanged
    assert (tmp_path / "Timelines" / "project.json").read_bytes() == project_before


def test_deploy_refuses_existing_project_without_overwrite(tmp_path, monkeypatch):
    import save_draft_impl

    monkeypatch.setattr(save_draft_impl, "get_capcut_projects_dir", lambda: str(tmp_path))
    (tmp_path / "Existing").mkdir()

    try:
        save_draft_impl.check_deploy_allowed("draft-1", "Existing")
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")
    save_draft_impl.check_deploy_allowed("draft-1", "Existing", overwrite=True)
    save_draft_impl.check_deploy_allowed("draft-1", "NewProject")
    # No deploy happens without auto_deploy or project_name, so nothing to refuse
    save_draft_impl.check_deploy_allowed("Existing", None, auto_deploy=False)

    result = save_draft_impl.save_draft_impl("draft-1", project_name="Existing")
    assert result["success"] is False and "already exists" in result["error"]
    assert (tmp_path / "Existing").is_dir()


def test_deploy_rejects_path_like_project_names(tmp_path, monkeypatch):
    import save_draft_impl

    monkeypatch.setattr(save_draft_impl, "get_capcut_projects_dir", lambda: str(tmp_path))
    for bad in ("../escape", "a/b", "..", "."):
        try:
            save_draft_impl.get_deploy_dir("draft-1", bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_TIMELINE_ID = "91E08AC5-22FB-47e2-9AA0-7DC300FAEA2B"


def _is_capcut_uuid(value):
    import uuid

    return value == value.upper() and str(uuid.UUID(value)).upper() == value


def test_new_script_files_get_unique_timeline_ids():
    import pyJianYingDraft as draft

    ids = {json.loads(draft.Script_file(1080, 1920).dumps())["id"] for _ in range(5)}

    assert len(ids) == 5
    assert TEMPLATE_TIMELINE_ID not in ids
    assert all(_is_capcut_uuid(value) for value in ids)


def test_load_template_keeps_existing_timeline_id(tmp_path):
    import pyJianYingDraft as draft

    existing = json.loads((REPO_ROOT / "pyJianYingDraft" / "draft_content_template.json").read_text(encoding="utf-8"))
    existing["id"] = "EXISTING-TIMELINE-ID"
    path = tmp_path / "draft_info.json"
    path.write_text(json.dumps(existing), encoding="utf-8")

    script = draft.Script_file.load_template(str(path))

    assert json.loads(script.dumps())["id"] == "EXISTING-TIMELINE-ID"


def test_template_copies_get_their_own_folder_ids(tmp_path):
    from draft_profiles import assign_new_draft_ids

    template = REPO_ROOT / "template"
    original_meta = json.loads((template / "draft_meta_info.json").read_text(encoding="utf-8"))
    original_tmp = json.loads((template / "template.tmp").read_text(encoding="utf-8"))
    seen = []
    for name in ("first", "second"):
        shutil.copytree(template, tmp_path / name)
        ids = assign_new_draft_ids(tmp_path / name)
        meta = json.loads((tmp_path / name / "draft_meta_info.json").read_text(encoding="utf-8"))
        tmp = json.loads((tmp_path / name / "template.tmp").read_text(encoding="utf-8"))
        assert meta["draft_id"] == ids["draft_id"] != original_meta["draft_id"]
        assert tmp["id"] == ids["template_tmp_id"] != original_tmp["id"]
        assert meta["draft_name"] == name
        assert meta["draft_fold_path"] == str((tmp_path / name).resolve())
        assert all(_is_capcut_uuid(value) for value in ids.values())
        seen.extend(ids.values())
    assert len(set(seen)) == 4
    # The template itself is untouched
    assert json.loads((template / "draft_meta_info.json").read_text(encoding="utf-8")) == original_meta


def test_folder_ids_skip_template_tmp_without_id(tmp_path):
    from draft_profiles import assign_new_draft_ids

    shutil.copytree(REPO_ROOT / "template_jianying_10_2", tmp_path / "draft")
    assign_new_draft_ids(tmp_path / "draft")

    assert "id" not in json.loads((tmp_path / "draft" / "template.tmp").read_text(encoding="utf-8"))


def test_capcut_mirrors_carry_the_new_timeline_id(tmp_path):
    from draft_profiles import get_draft_profile, write_profile_content

    shutil.copytree(REPO_ROOT / "template", tmp_path / "draft")
    payload = {"id": "NEW-TIMELINE-ID", "tracks": [], "materials": {}}

    write_profile_content(get_draft_profile("capcut_legacy"), tmp_path / "draft", json.dumps(payload))

    for name in ("draft_info.json", "draft_info.json.bak", "template-2.tmp"):
        assert json.loads((tmp_path / "draft" / name).read_text(encoding="utf-8"))["id"] == "NEW-TIMELINE-ID"


def test_relocate_draft_paths_rewrites_only_build_folder_paths(tmp_path):
    from draft_profiles import find_draft_paths, relocate_draft_paths

    build, deployed = tmp_path / "build" / "draft-1", tmp_path / "capcut" / "Project"
    deployed.mkdir(parents=True)
    clip = str(build / "assets" / "video" / "clip.mp4")
    content = {
        "materials": {"videos": [{"path": clip}], "audios": [{"path": "/elsewhere/song.mp3"}]},
        "nested": [{"cover": str(build / "draft_cover.jpg")}],
        "name": "draft-1",
    }
    for name in ("draft_info.json", "draft_info.json.bak"):
        (deployed / name).write_text(json.dumps(content), encoding="utf-8")
    (deployed / "notes.txt").write_text(clip, encoding="utf-8")

    changed = relocate_draft_paths(deployed, build, deployed)

    assert sorted(path.name for path in changed) == ["draft_info.json", "draft_info.json.bak"]
    data = json.loads((deployed / "draft_info.json").read_text(encoding="utf-8"))
    assert data["materials"]["videos"][0]["path"] == str(deployed / "assets" / "video" / "clip.mp4")
    assert data["nested"][0]["cover"] == str(deployed / "draft_cover.jpg")
    assert data["materials"]["audios"][0]["path"] == "/elsewhere/song.mp3"
    assert data["name"] == "draft-1"
    assert find_draft_paths(deployed, build) == []
    # Only JSON files are rewritten
    assert (deployed / "notes.txt").read_text(encoding="utf-8") == clip


def _save_with_fake_media(tmp_path, monkeypatch, draft_id, create_media):
    import save_draft_impl
    from draft_cache import DRAFT_CACHE
    from draft_profiles import get_draft_profile

    build_root, capcut_root = tmp_path / "build", tmp_path / "capcut"
    capcut_root.mkdir()
    clip = build_root / draft_id / "assets" / "video" / "clip.mp4"
    source = str(tmp_path / "source" / "clip.mp4")  # a local video_url, like the real workflow
    payload = {"tracks": [{"type": "video"}], "duration": 1,
               "materials": {"videos": [{"path": str(clip), "remote_url": source}]}}

    def fake_media_step(script, task_id=None):
        # Runs after the template copy, where real downloads would land
        if create_media:
            clip.parent.mkdir(parents=True, exist_ok=True)
            clip.write_bytes(b"fake video")

    DRAFT_CACHE[draft_id] = SimpleNamespace(
        materials=SimpleNamespace(audios=[], videos=[]), tracks={},
        dumps=lambda profile=None: json.dumps(payload),
    )
    monkeypatch.setattr(save_draft_impl, "get_capcut_projects_dir", lambda: str(capcut_root))
    monkeypatch.setattr(save_draft_impl, "get_draft_profile", lambda: get_draft_profile("capcut_legacy"))
    monkeypatch.setattr(save_draft_impl, "update_media_metadata", fake_media_step)
    monkeypatch.setattr(save_draft_impl, "IS_UPLOAD_DRAFT", False)
    result = save_draft_impl.save_draft_impl(draft_id, str(build_root), project_name="Deployed")
    return result, build_root / draft_id, capcut_root / "Deployed", clip


def test_deploy_points_media_at_the_deployed_project(tmp_path, monkeypatch):
    from draft_profiles import find_draft_paths

    result, build_dir, deployed, clip = _save_with_fake_media(tmp_path, monkeypatch, "draft-media-ok", True)

    assert result["success"] is True
    deployed_clip = deployed / "assets" / "video" / "clip.mp4"
    assert deployed_clip.read_bytes() == b"fake video"
    for name in ("draft_info.json", "draft_info.json.bak", "template-2.tmp"):
        data = json.loads((deployed / name).read_text(encoding="utf-8"))
        assert data["materials"]["videos"][0]["path"] == str(deployed_clip)
        assert data["materials"]["videos"][0]["remote_url"] == str(deployed_clip)
    assert find_draft_paths(deployed, build_dir) == []
    assert find_draft_paths(deployed, tmp_path / "source") == []
    # The build draft is left as it was
    build_data = json.loads((build_dir / "draft_info.json").read_text(encoding="utf-8"))
    assert build_data["materials"]["videos"][0]["path"] == str(clip)
    assert build_data["materials"]["videos"][0]["remote_url"] == str(tmp_path / "source" / "clip.mp4")


def test_deploy_fails_when_media_is_missing(tmp_path, monkeypatch):
    result, _, _, _ = _save_with_fake_media(tmp_path, monkeypatch, "draft-media-missing", False)

    assert result["success"] is False
    assert "media that does not exist" in result["error"]


def test_localize_material_sources_keeps_real_urls(tmp_path):
    from draft_profiles import localize_material_sources

    content = {"materials": {
        "videos": [{"path": "/proj/assets/video/a.mp4", "remote_url": "/Users/me/Desktop/a.mp4"}],
        "audios": [{"path": "/proj/assets/audio/b.mp3", "remote_url": "https://example.com/b.mp3"}],
    }}
    (tmp_path / "draft_info.json").write_text(json.dumps(content), encoding="utf-8")

    assert localize_material_sources(tmp_path) == [tmp_path / "draft_info.json"]
    data = json.loads((tmp_path / "draft_info.json").read_text(encoding="utf-8"))
    assert data["materials"]["videos"][0]["remote_url"] == "/proj/assets/video/a.mp4"
    assert data["materials"]["audios"][0]["remote_url"] == "https://example.com/b.mp3"
