"""PII anonymization engine — 16 regex rules applied in sequence."""

from __future__ import annotations

import re


class Anonymizer:
    """Removes personally identifiable information from text."""

    def anonymize(
        self,
        text: str,
        company_domain: str = "",
        company_aliases: list[str] | None = None,
        person_names: list[str] | None = None,
    ) -> str:
        """Apply all 16 anonymization rules in sequence."""
        if not text:
            return text

        aliases = company_aliases or []
        names = person_names or []

        # Rule 1: email → [email]
        text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[email]', text)

        # Rule 2: URL → [URL]
        text = re.sub(r'https?://\S+', '[URL]', text)

        # Rule 3: IP → [IP]
        text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', text)

        # Rule 4: 稱謂+姓名（您好 XXX、Dear XXX）→ 您好 / Dear
        text = re.sub(r'(您好\s*)[^\s,，。\n]{2,4}', r'\1', text)
        text = re.sub(r'(Dear\s+)\w+', r'\1', text, flags=re.IGNORECASE)

        # Rule 5: 寄件人簽名行（From: / 寄件人：後面整行）→ remove
        text = re.sub(r'^(From:|寄件人[：:]).*$', '', text, flags=re.MULTILINE)

        # Rule 6: 完整姓名+公司（XXX 先生/小姐 from YYY）→ 相關人員
        text = re.sub(r'[\u4e00-\u9fff]{2,4}\s*(先生|小姐|經理|主管)\s*(from|來自)\s*\S+', '相關人員', text)

        # Rule 7: 客戶公司英文域名 → 貴客戶
        if company_domain:
            text = re.sub(re.escape(company_domain), '貴客戶', text, flags=re.IGNORECASE)

        # Rule 8: CS 人員識別詞（from HCP、by 客服）→ remove
        text = re.sub(r'(from\s+HCP|by\s*客服).*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

        # Rule 9: Hi/Hello [英文名] → Hi/Hello
        text = re.sub(r'(Hi|Hello)\s+[A-Z][a-z]+', r'\1', text)

        # Rule 10: 敬啟者/致 → remove line
        text = re.sub(r'^(敬啟者|致\s+\S+).*$', '', text, flags=re.MULTILINE)

        # Rule 11: Best regards/Thanks + 姓名 → remove
        text = re.sub(r'(Best\s+regards|Thanks|Thank\s+you|此致|敬上)[,，\s]*[\w\u4e00-\u9fff]*', '', text, flags=re.IGNORECASE)

        # Rule 12: 職稱+中文姓名（工程師 XXX、承辦人 XXX）→ 相關人員
        text = re.sub(r'(工程師|承辦人|負責人|專員|主管|經理|組長|課長|處長)\s*[\u4e00-\u9fff]{2,4}', '相關人員', text)

        # Rule 13: 姓名|職稱格式（簽名欄）→ （簽名已略）
        text = re.sub(r'^[\u4e00-\u9fff]{2,4}\s*[|｜]\s*(工程師|專員|主管|經理).*$', '（簽名已略）', text, flags=re.MULTILINE)

        # Rule 14: 獨立英文人名（單行, capitalized）→ 相關人員
        text = re.sub(r'^[A-Z][a-z]+\s+[A-Z][a-z]+\s*$', '相關人員', text, flags=re.MULTILINE)

        # Rule 15: 公司中文別名 → 貴客戶
        for alias in aliases:
            if alias:
                text = re.sub(re.escape(alias), '貴客戶', text)

        # Rule 16: 獨立 2-4 個中文字（單行姓名）→ 相關人員
        text = re.sub(r'^[\u4e00-\u9fff]{2,4}\s*$', '相關人員', text, flags=re.MULTILINE)

        # Clean up: remove excessive blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()
