"""tests/unit/test_supplement_enrichment.py — 補充說明強化功能測試。"""

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
