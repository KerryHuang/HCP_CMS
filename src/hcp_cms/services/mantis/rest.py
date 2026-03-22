"""Mantis REST API client."""

from __future__ import annotations

import requests

from hcp_cms.services.mantis.base import MantisClient, MantisIssue


class MantisRESTClient(MantisClient):
    def __init__(self, base_url: str, api_token: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._session: requests.Session | None = None

    def connect(self) -> bool:
        try:
            self._session = requests.Session()
            self._session.headers["Authorization"] = self._api_token
            resp = self._session.get(f"{self._base_url}/api/rest/users/me", timeout=10)
            return resp.status_code == 200
        except Exception:
            self._session = None
            return False

    def get_issue(self, issue_id: str) -> MantisIssue | None:
        if not self._session:
            return None
        try:
            resp = self._session.get(f"{self._base_url}/api/rest/issues/{issue_id}", timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json().get("issues", [{}])[0]
            return MantisIssue(
                id=str(data.get("id", "")),
                summary=data.get("summary", ""),
                status=data.get("status", {}).get("name", ""),
                priority=data.get("priority", {}).get("name", ""),
                handler=data.get("handler", {}).get("name", ""),
            )
        except Exception:
            return None

    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]:
        if not self._session:
            return []
        try:
            url = f"{self._base_url}/api/rest/issues"
            params = {"page_size": 100}
            if project_id:
                params["project_id"] = project_id
            resp = self._session.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                return []
            return [
                MantisIssue(
                    id=str(d.get("id", "")),
                    summary=d.get("summary", ""),
                    status=d.get("status", {}).get("name", ""),
                    priority=d.get("priority", {}).get("name", ""),
                )
                for d in resp.json().get("issues", [])
            ]
        except Exception:
            return []
