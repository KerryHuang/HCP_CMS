"""Mantis client abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MantisNote:
    """單條 Mantis Bug 筆記。"""

    note_id: str = ""
    reporter: str = ""
    text: str = ""
    date_submitted: str = ""


@dataclass
class MantisIssue:
    """Parsed Mantis issue data."""

    id: str
    summary: str
    status: str = ""
    priority: str = ""
    handler: str = ""
    severity: str = ""
    reporter: str = ""
    date_submitted: str = ""  # 原 created 欄位改名，語意統一
    last_updated: str = ""  # Mantis 最後更新時間
    target_version: str = ""
    fixed_in_version: str = ""
    description: str = ""
    notes_list: list[MantisNote] = field(default_factory=list)
    notes_count: int = 0  # SOAP 回傳的筆記總數（不受 max_count 限制）


class MantisClient(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def get_issue(self, issue_id: str) -> MantisIssue | None: ...

    @abstractmethod
    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]: ...

    @abstractmethod
    def create_issue(
        self,
        project_id: str,
        summary: str,
        description: str,
        category: str = "",
        priority: str = "normal",
        severity: str = "minor",
        handler: str | None = None,
    ) -> str | None:
        """建立新 issue，成功回傳 ticket_id，失敗回 None（self.last_error 含原因）。"""

    @abstractmethod
    def add_note(
        self,
        issue_id: str,
        text: str,
        view_state: str = "public",
    ) -> str | None:
        """加 bugnote，成功回傳 note_id，失敗回 None。"""
