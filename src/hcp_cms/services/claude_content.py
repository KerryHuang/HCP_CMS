"""ClaudeContentService — 使用 Claude API 生成說明文字與通知信內容。"""

from __future__ import annotations

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[assignment,misc]

_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 3
_SUPPLEMENT_KEYS = ("修改原因", "原問題", "範例說明", "修正後", "注意事項")


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

    def extract_supplement(self, mantis_text: str) -> dict[str, str]:
        """分析 Mantis Issue 說明，回傳結構化補充說明五欄位。"""
        empty = {k: "" for k in _SUPPLEMENT_KEYS}
        if self._client is None or not mantis_text.strip():
            return empty
        prompt = (
            "請根據以下 Mantis Issue 說明文字，以繁體中文提取並整理下列五個欄位，"
            "以 JSON 格式回傳，key 為繁體中文欄位名稱：\n"
            "欄位：修改原因、原問題、範例說明、修正後、注意事項\n"
            "若某欄位無對應內容則值為空字串。只回傳 JSON，不要其他說明。\n\n"
            f"Mantis 說明：\n{mantis_text}"
        )
        raw = self._call_api(prompt, max_tokens=600)
        if not raw:
            return empty
        try:
            import json
            import re
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
