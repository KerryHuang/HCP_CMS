"""MantisClient 抽象介面"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MantisTicket:
    """Mantis 工單資料結構"""

    ticket_id: int
    summary: str
    description: str
    status: str
    priority: str
    category: str
    reporter: str
    assigned_to: str | None = None


class MantisClient(ABC):
    """Mantis 服務抽象介面"""

    @abstractmethod
    def get_tickets(self, project_id: int) -> list[MantisTicket]:
        """取得工單列表"""

    @abstractmethod
    def get_ticket(self, ticket_id: int) -> MantisTicket:
        """取得單一工單"""

    @abstractmethod
    def sync_tickets(self, project_id: int) -> int:
        """同步工單，回傳新增/更新數量"""
