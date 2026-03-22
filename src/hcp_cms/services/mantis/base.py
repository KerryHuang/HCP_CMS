"""Mantis client abstract interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MantisIssue:
    """Parsed Mantis issue data."""
    id: str
    summary: str
    status: str = ""
    priority: str = ""
    handler: str = ""
    notes: str = ""
    created: str = ""


class MantisClient(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def get_issue(self, issue_id: str) -> MantisIssue | None: ...

    @abstractmethod
    def get_issues(self, project_id: str | None = None) -> list[MantisIssue]: ...
