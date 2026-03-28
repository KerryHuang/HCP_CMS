"""Mantis SOAP API client."""

from __future__ import annotations

import re

import requests
import urllib3

from hcp_cms.services.mantis.base import MantisClient, MantisIssue, MantisNote

# 忽略自簽 SSL 憑證警告（內網 Mantis 伺服器常見）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MantisSoapClient(MantisClient):
    def __init__(self, base_url: str, username: str = "", password: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._connected = False
        self.last_error: str = ""

    def connect(self) -> bool:
        """測試 SOAP 端點是否可達。"""
        try:
            resp = requests.get(
                f"{self._base_url}/api/soap/mantisconnect.php",
                timeout=10,
                verify=False,
            )
            self._connected = resp.status_code in (200, 400, 405, 500)
            return self._connected
        except Exception as e:
            self.last_error = str(e)
            self._connected = False
            return False

    def get_issue(self, issue_id: str) -> MantisIssue | None:
        if not self._connected:
            self.last_error = "尚未連線，請先呼叫 connect()"
            return None
        soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:man="http://futureware.biz/mantisconnect">
    <soapenv:Body>
        <man:mc_issue_get>
            <man:username>{self._username}</man:username>
            <man:password>{self._password}</man:password>
            <man:issue_id>{issue_id}</man:issue_id>
        </man:mc_issue_get>
    </soapenv:Body>
</soapenv:Envelope>"""
        try:
            resp = requests.post(
                f"{self._base_url}/api/soap/mantisconnect.php",
                data=soap_body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=30,
                verify=False,
            )
            if resp.status_code != 200:
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return None

            text = resp.text
            if "<faultstring>" in text:
                fault = self._extract_xml(text, "faultstring") or "未知錯誤"
                self.last_error = f"SOAP 錯誤：{fault}"
                return None

            summary = self._extract_xml(text, "summary") or ""
            if not summary:
                self.last_error = "回應內容解析失敗（summary 為空）"
                return None

            status = self._extract_xml(text, "name", after="status") or ""
            priority = self._extract_xml(text, "name", after="priority") or ""
            handler = self._extract_xml(text, "name", after="handler") or ""
            severity = self._extract_xml(text, "name", after="severity") or ""
            reporter = self._extract_xml(text, "name", after="reporter") or ""
            date_submitted = self._extract_xml(text, "date_submitted") or ""
            last_updated = self._extract_xml(text, "last_updated") or ""
            target_version = self._extract_xml(text, "target_version") or ""
            fixed_in_version = self._extract_xml(text, "fixed_in_version") or ""
            description = self._extract_xml(text, "description") or ""

            notes_list, notes_count = self._parse_notes(text, max_count=5)

            return MantisIssue(
                id=issue_id,
                summary=summary,
                status=status,
                priority=priority,
                handler=handler,
                severity=severity,
                reporter=reporter,
                date_submitted=date_submitted,
                last_updated=last_updated,
                target_version=target_version,
                fixed_in_version=fixed_in_version,
                description=description,
                notes_list=notes_list,
                notes_count=notes_count,
            )
        except requests.exceptions.SSLError as e:
            self.last_error = f"SSL 憑證錯誤：{e}"
            return None
        except requests.exceptions.ConnectionError as e:
            self.last_error = f"連線失敗：{e}"
            return None
        except requests.exceptions.Timeout:
            self.last_error = "連線逾時（30 秒）"
            return None
        except Exception as e:
            self.last_error = f"未知錯誤：{e}"
            return None

    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]:
        return []

    @staticmethod
    def _extract_xml(text: str, tag: str, after: str | None = None) -> str | None:
        if after:
            m = re.search(f"<{after}[^>]*>", text)
            if m is None:
                return None
            text = text[m.start() :]
        match = re.search(f"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL)
        return match.group(1).strip() if match else None

    @staticmethod
    def _parse_notes(text: str, max_count: int = 5) -> tuple[list[MantisNote], int]:
        """解析 SOAP 回應中的所有 <item>（Bug 筆記），返回最後 max_count 條（降序）與總數。"""
        notes_match = re.search(r"<notes[^>]*>(.*?)</notes>", text, re.DOTALL)
        if not notes_match:
            return [], 0

        notes_block = notes_match.group(1)
        items = re.findall(r"<item[^>]*>(.*?)</item>", notes_block, re.DOTALL)
        total = len(items)

        def _extract(block: str, tag: str, after: str | None = None) -> str:
            return MantisSoapClient._extract_xml(block, tag, after) or ""

        notes: list[MantisNote] = []
        for item in items:
            notes.append(
                MantisNote(
                    note_id=_extract(item, "id"),
                    reporter=_extract(item, "name", after="reporter"),
                    text=_extract(item, "text"),
                    date_submitted=_extract(item, "date_submitted"),
                )
            )

        # 取最後 max_count 條，依 date_submitted 降序（最新在前）
        tail = notes[-max_count:] if len(notes) > max_count else notes
        tail_sorted = sorted(tail, key=lambda n: n.date_submitted, reverse=True)
        return tail_sorted, total
