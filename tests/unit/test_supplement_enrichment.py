"""tests/unit/test_supplement_enrichment.py — 補充說明強化功能測試。"""

import pytest

# ── Task 1: ClaudeContentService ──────────────────────────────────────────

def test_extract_supplement_no_client():
    """Claude client 為 None 時回傳全空 dict，不呼叫 API。"""
    from hcp_cms.services.claude_content import ClaudeContentService
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = None
    result = svc.extract_supplement(
        release_note_description="有內容",
        mantis_description="有描述",
    )
    assert result == {"修改原因": "", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}


def test_extract_supplement_all_sources(monkeypatch):
    """三來源皆有資料時，五欄位均有輸出，prompt 包含各來源文字。"""
    from hcp_cms.services.claude_content import ClaudeContentService
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = object()  # 非 None
    captured: dict = {}

    def fake_call(prompt: str, max_tokens: int) -> str:
        captured["prompt"] = prompt
        return '{"修改原因":"A","原問題":"B","範例說明":"C","修正後":"D","注意事項":"E"}'

    monkeypatch.setattr(svc, "_call_api", fake_call)
    result = svc.extract_supplement(
        release_note_description="薪資計算異常",
        release_note_impact="影響 HR 模組",
        mantis_description="員工點薪資查詢時系統報錯",
        mantis_notes=[{"reporter": "工程師A", "date": "2026-03-15", "text": "已修正第220行邏輯"}],
    )
    assert result["修改原因"] == "A"
    assert result["注意事項"] == "E"
    assert "薪資計算異常" in captured["prompt"]
    assert "員工點薪資查詢" in captured["prompt"]
    assert "工程師A" in captured["prompt"]
    assert "欄位定義" in captured["prompt"]


def test_extract_supplement_sparse_data(monkeypatch):
    """三來源合計有效字 < 30 時，prompt 包含稀疏資料提示。"""
    from hcp_cms.services.claude_content import ClaudeContentService
    svc = ClaudeContentService.__new__(ClaudeContentService)
    svc._client = object()
    captured: dict = {}

    def fake_call(prompt: str, max_tokens: int) -> str:
        captured["prompt"] = prompt
        return '{"修改原因":"⚠ 資料不足，請人工補充","原問題":"","範例說明":"","修正後":"","注意事項":""}'

    monkeypatch.setattr(svc, "_call_api", fake_call)
    svc.extract_supplement(
        release_note_description="短",
        release_note_impact="",
        mantis_description="",
        mantis_notes=[],
    )
    assert "以上資料非常有限" in captured["prompt"]


# ── Task 2: MantisSoapClient ───────────────────────────────────────────────

def test_parse_notes_limit_10():
    """_parse_notes 應保留最後 10 條筆記。"""
    from hcp_cms.services.mantis.soap import MantisSoapClient
    # 建立 12 條假筆記的 XML
    items_xml = "".join(
        f"<item><id>{i}</id><reporter><name>u{i}</name></reporter>"
        f"<text>note{i}</text><date_submitted>2026-03-{i:02d}T00:00:00Z</date_submitted></item>"
        for i in range(1, 13)
    )
    xml = f"<notes>{items_xml}</notes>"
    notes, total = MantisSoapClient._parse_notes(xml, max_count=10)
    assert total == 12
    assert len(notes) == 10


# ── Task 3: PatchRepository ────────────────────────────────────────────────

@pytest.fixture
def db_conn(tmp_path):
    from hcp_cms.data.database import DatabaseManager
    db = DatabaseManager(str(tmp_path / "test.db"))
    db.initialize()
    yield db._conn
    db.close()


def test_update_issue_supplement_auto(db_conn):
    """auto 模式（manual=False）儲存 supplement，supplement_edited 保持 False。"""
    import json

    from hcp_cms.data.models import PatchIssue, PatchRecord
    from hcp_cms.data.repositories import PatchRepository
    repo = PatchRepository(db_conn)
    patch_id = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
    issue_id = repo.insert_issue(PatchIssue(patch_id=patch_id, issue_no="0017023"))

    supplement = {"修改原因": "自動填入", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    repo.update_issue_supplement(issue_id, supplement, manual=False)

    updated = repo.get_issue_by_id(issue_id)
    detail = json.loads(updated.mantis_detail)
    assert detail["supplement"]["修改原因"] == "自動填入"
    assert detail.get("supplement_edited", False) is False


def test_update_issue_supplement_manual(db_conn):
    """manual=True 時 supplement_edited 旗標設為 True。"""
    import json

    from hcp_cms.data.models import PatchIssue, PatchRecord
    from hcp_cms.data.repositories import PatchRepository
    repo = PatchRepository(db_conn)
    patch_id = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
    issue_id = repo.insert_issue(PatchIssue(patch_id=patch_id, issue_no="0017023"))

    supplement = {"修改原因": "人工修改", "原問題": "B", "範例說明": "C", "修正後": "D", "注意事項": "E"}
    repo.update_issue_supplement(issue_id, supplement, manual=True)

    updated = repo.get_issue_by_id(issue_id)
    detail = json.loads(updated.mantis_detail)
    assert detail["supplement"]["修改原因"] == "人工修改"
    assert detail["supplement_edited"] is True


def test_update_issue_supplement_preserves_existing_fields(db_conn):
    """update_issue_supplement 保留既有 mantis_detail 其他欄位（如 form_files）。"""
    import json

    from hcp_cms.data.models import PatchIssue, PatchRecord
    from hcp_cms.data.repositories import PatchRepository
    repo = PatchRepository(db_conn)
    patch_id = repo.insert_patch(PatchRecord(type="monthly", month_str="202604"))
    existing_detail = json.dumps({"form_files": ["HRWF304"], "archive_name": "01.IP_11G.7z"})
    issue_id = repo.insert_issue(PatchIssue(
        patch_id=patch_id, issue_no="0017023", mantis_detail=existing_detail
    ))

    supplement = {"修改原因": "測試", "原問題": "", "範例說明": "", "修正後": "", "注意事項": ""}
    repo.update_issue_supplement(issue_id, supplement, manual=False)

    updated = repo.get_issue_by_id(issue_id)
    detail = json.loads(updated.mantis_detail)
    assert detail["form_files"] == ["HRWF304"]        # 原有欄位保留
    assert detail["supplement"]["修改原因"] == "測試"  # 新欄位寫入
