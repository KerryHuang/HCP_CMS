"""ClaudeContentService — 使用 Claude API 生成說明文字與通知信內容。"""

from __future__ import annotations

import json
import re

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[assignment,misc]

_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 3
_SUPPLEMENT_KEYS = ("修改原因", "原問題", "範例說明", "修正後", "注意事項")
_INSUFFICIENT = "⚠ 資料不足，請人工補充"
_SPARSE_THRESHOLD = 30  # 有效字數低於此值時加入稀疏提示


class ClaudeContentService:
    def __init__(self) -> None:
        from hcp_cms.services.credential import CredentialManager
        api_key = CredentialManager().retrieve("claude_api_key")
        if api_key and Anthropic is not None:
            self._client = Anthropic(api_key=api_key)
        else:
            self._client = None

    def generate_description(self, issue_data: dict) -> str | None:
        """依 Issue 資料生成 HR 版功能說明文字（50-100字）。"""
        if self._client is None:
            return None
        prompt = (
            f"請根據以下 HCP Issue 資訊，用繁體中文撰寫一段簡潔的功能說明（50-100字）：\n"
            f"Issue No: {issue_data.get('issue_no', '')}\n"
            f"說明: {issue_data.get('description', '')}\n"
            f"類型: {issue_data.get('issue_type', '')}"
        )
        return self._call_api(prompt, max_tokens=300)

    def generate_notify_body(self, issues: list[dict], month_str: str) -> str | None:
        """依 Issue 清單生成客戶通知信主體段落。"""
        if self._client is None:
            return None
        year = month_str[:4]
        month = month_str[4:]
        summary = "\n".join(
            f"- {i.get('issue_no', '')}: {i.get('description', '')}" for i in issues
        )
        prompt = (
            f"請根據以下 {year}年{month}月 HCP 大PATCH Issue 清單，"
            f"撰寫一段給客戶的更新說明（繁體中文，說明各項修正的業務影響）：\n{summary}"
        )
        return self._call_api(prompt, max_tokens=800)

    def extract_supplement(
        self,
        release_note_description: str = "",
        release_note_impact: str = "",
        mantis_description: str = "",
        mantis_notes: list[dict] | None = None,
    ) -> dict[str, str]:
        """分析三來源資料，回傳結構化補充說明五欄位。

        mantis_notes: list of {"reporter": str, "date": str, "text": str}
        """
        empty = {k: "" for k in _SUPPLEMENT_KEYS}
        if self._client is None:
            return empty

        notes_list = mantis_notes or []
        if notes_list:
            notes_text = "\n".join(
                f"[{n.get('date', '')}] {n.get('reporter', '')}：{n.get('text', '')}"
                for n in notes_list
            )
        else:
            notes_text = "（無活動記錄）"

        all_text = " ".join([
            release_note_description, release_note_impact,
            mantis_description, notes_text,
        ])
        effective_chars = len(all_text.replace(" ", "").replace("　", "").replace("\n", ""))
        sparse_hint = (
            "\n⚠ 注意：以上資料非常有限，若無法合理填寫請直接填入資料不足標記。"
            if effective_chars < _SPARSE_THRESHOLD else ""
        )

        prompt = (
            "你是 HCP ERP 系統的技術文件分析助理。\n"
            "請根據以下來自三個來源的資料，以繁體中文填寫五個補充說明欄位。\n\n"
            "【欄位定義】\n"
            f"- 修改原因：此次修改的業務或技術背景，解釋「為什麼要改」\n"
            f"- 原問題：修改前系統存在的問題現象，解釋「原本出了什麼問題」\n"
            f"- 範例說明：具體操作情境或資料範例（如有）\n"
            f"- 修正後：修改後的行為或效果說明\n"
            f"- 注意事項：上線後測試重點、注意事項或相依模組\n\n"
            f"【資料：ReleaseNote 說明】\n"
            f"功能說明：{release_note_description or '（無）'}\n"
            f"影響說明：{release_note_impact or '（無）'}\n\n"
            f"【資料：Mantis 問題描述】\n"
            f"{mantis_description or '（無）'}\n\n"
            f"【資料：Mantis 活動筆記（依時間排列）】\n"
            f"{notes_text}"
            f"{sparse_hint}\n\n"
            f"請以 JSON 格式回傳，key 為繁體中文欄位名稱。\n"
            f'若某欄位無對應內容且無法合理推斷，值填入「{_INSUFFICIENT}」。\n'
            f"只回傳 JSON，不要其他說明。"
        )
        raw = self._call_api(prompt, max_tokens=800)
        if not raw:
            return empty
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return empty
            data = json.loads(match.group())
            return {k: str(data.get(k) or "") for k in _SUPPLEMENT_KEYS}
        except (ValueError, KeyError):
            return empty

    def _call_api(self, prompt: str, max_tokens: int) -> str | None:
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.messages.create(  # type: ignore[union-attr]
                    model=_MODEL,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except Exception:
                if attempt == _MAX_RETRIES - 1:
                    return None
        return None
