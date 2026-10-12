def _save_draft_tool(monkeypatch, arguments, impl_result=None):
    import mcp_server

    calls = []

    def fake_save_draft_impl(draft_id, draft_folder=None, project_name=None, auto_deploy=True, overwrite=False):
        calls.append({"draft_id": draft_id, "draft_folder": draft_folder, "project_name": project_name,
                      "auto_deploy": auto_deploy, "overwrite": overwrite})
        return impl_result or {"success": True, "draft_url": f"/capcut/{project_name or draft_id}"}

    monkeypatch.setattr(mcp_server, "save_draft_impl", fake_save_draft_impl)
    monkeypatch.setattr(mcp_server, "CAPCUT_AVAILABLE", True)
    return mcp_server.execute_tool("save_draft", arguments), calls


def test_save_draft_schema_declares_overwrite():
    import mcp_server

    schema = next(tool for tool in mcp_server.TOOLS if tool["name"] == "save_draft")["inputSchema"]

    assert schema["properties"]["overwrite"]["type"] == "boolean"
    assert schema["properties"]["overwrite"]["default"] is False
    assert {"project_name", "auto_deploy", "draft_folder"} <= set(schema["properties"])
    assert schema["required"] == ["draft_id"]


def test_save_draft_passes_overwrite_true(monkeypatch):
    response, calls = _save_draft_tool(monkeypatch, {"draft_id": "d1", "project_name": "P", "overwrite": True})

    assert response["success"] is True
    assert response["result"] == {"draft_url": "/capcut/P"}
    assert calls == [{"draft_id": "d1", "draft_folder": None, "project_name": "P", "auto_deploy": True, "overwrite": True}]


def test_save_draft_only_boolean_true_overwrites(monkeypatch):
    for value in ("true", 1, "yes", None):
        _, calls = _save_draft_tool(monkeypatch, {"draft_id": "d1", "project_name": "P", "overwrite": value})
        assert calls[0]["overwrite"] is False, value

    _, calls = _save_draft_tool(monkeypatch, {"draft_id": "d1", "project_name": "P"})
    assert calls[0]["overwrite"] is False


def test_save_draft_reports_refusal_instead_of_success(monkeypatch):
    refusal = {"success": False, "error": "CapCut project already exists: /capcut/P"}

    response, _ = _save_draft_tool(monkeypatch, {"draft_id": "d1", "project_name": "P"}, impl_result=refusal)

    assert response == {"success": False, "error": "CapCut project already exists: /capcut/P"}


def test_save_draft_ignores_unknown_arguments_and_requires_draft_id(monkeypatch):
    response, calls = _save_draft_tool(monkeypatch, {"draft_id": "d1", "auto_reload": True})
    assert response["success"] is True and calls[0]["draft_id"] == "d1"

    response, calls = _save_draft_tool(monkeypatch, {"project_name": "P"})
    assert response["success"] is False and "draft_id" in response["error"] and calls == []
