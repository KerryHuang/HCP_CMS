"""Mantis SOAP API client."""

from __future__ import annotations

import re

import requests
import urllib3

from hcp_cms.services.mantis.base import MantisClient, MantisIssue

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
                verify=False,  # 允許自簽憑證
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
                verify=False,  # 允許自簽憑證
            )
            if resp.status_code != 200:
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return None

            text = resp.text
            # 檢查是否為 SOAP Fault（錯誤回應）
            if "<faultstring>" in text:
                fault = self._extract_xml(text, "faultstring") or "未知錯誤"
                self.last_error = f"SOAP 錯誤：{fault}"
                return None

            summary = self._extract_xml(text, "summary") or ""
            status = self._extract_xml(text, "name", after="status") or ""
            priority = self._extract_xml(text, "name", after="priority") or ""
            handler = self._extract_xml(text, "name", after="handler") or ""

            if not summary:
                self.last_error = "回應內容解析失敗（summary 為空）"
                return None

            return MantisIssue(
                id=issue_id,
                summary=summary,
                status=status,
                priority=priority,
                handler=handler,
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
            idx = text.find(f"<{after}>")
            if idx == -1:
                return None
            text = text[idx:]
        match = re.search(f"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        return match.group(1).strip() if match else None
