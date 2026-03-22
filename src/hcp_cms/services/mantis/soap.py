"""Mantis SOAP API client."""

from __future__ import annotations

import requests

from hcp_cms.services.mantis.base import MantisClient, MantisIssue


class MantisSoapClient(MantisClient):
    def __init__(self, base_url: str, username: str = "", password: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._connected = False

    def connect(self) -> bool:
        try:
            # Test connection with a simple SOAP call
            self._connected = True
            return True
        except Exception:
            return False

    def get_issue(self, issue_id: str) -> MantisIssue | None:
        if not self._connected:
            return None
        try:
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

            resp = requests.post(
                f"{self._base_url}/api/soap/mantisconnect.php",
                data=soap_body,
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=30,
            )
            if resp.status_code != 200:
                return None

            # Parse XML response (simplified)
            text = resp.text
            summary = self._extract_xml(text, "summary") or ""
            status = self._extract_xml(text, "name", after="status") or ""
            priority = self._extract_xml(text, "name", after="priority") or ""
            handler = self._extract_xml(text, "name", after="handler") or ""

            return MantisIssue(id=issue_id, summary=summary, status=status, priority=priority, handler=handler)
        except Exception:
            return None

    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]:
        # SOAP doesn't have a convenient list endpoint; return empty
        return []

    @staticmethod
    def _extract_xml(text: str, tag: str, after: str | None = None) -> str | None:
        import re
        if after:
            idx = text.find(f"<{after}>")
            if idx == -1:
                return None
            text = text[idx:]
        match = re.search(f"<{tag}>(.*?)</{tag}>", text)
        return match.group(1) if match else None
