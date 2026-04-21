"""Data models for HCP CMS — all entities as dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field

SLA_HOURS_NORMAL = 24
SLA_HOURS_HIGH = 4
SLA_HOURS_CUSTOM = 48


@dataclass
class Case:
    """客服案件 — cs_cases table."""
    case_id: str
    subject: str
    contact_method: str = "Email"
    status: str = "處理中"
    priority: str = "中"
    sent_time: str | None = None
    company_id: str | None = None
    contact_person: str | None = None
    system_product: str | None = None
    issue_type: str | None = None
    error_type: str | None = None
    impact_period: str | None = None
    progress: str | None = None
    actual_reply: str | None = None
    reply_time: str | None = None
    notes: str | None = None
    rd_assignee: str | None = None
    handler: str | None = None
    reply_count: int = 0
    linked_case_id: str | None = None
    source: str = "email"
    created_at: str | None = None
    updated_at: str | None = None
    extra_fields: dict[str, str | None] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status not in ("已完成", "Closed")

    @property
    def sla_hours(self) -> int:
        if self.issue_type == "客制需求":
            return SLA_HOURS_CUSTOM
        if self.priority == "高":
            return SLA_HOURS_HIGH
        return SLA_HOURS_NORMAL


@dataclass
class Company:
    company_id: str
    name: str
    domain: str
    alias: str | None = None
    contact_info: str | None = None
    cs_staff_id: str | None = None      # FK → staff.staff_id（負責客服）
    sales_staff_id: str | None = None   # FK → staff.staff_id（負責業務）
    hcp_version: str | None = None      # 從 Mantis 同步的 HcpVersion
    created_at: str | None = None


@dataclass
class QAKnowledge:
    qa_id: str
    question: str
    answer: str
    system_product: str | None = None
    issue_type: str | None = None
    error_type: str | None = None
    solution: str | None = None
    keywords: str | None = None
    has_image: str = "否"
    doc_name: str | None = None
    company_id: str | None = None
    source_case_id: str | None = None
    source: str = "manual"
    status: str = "已完成"    # '待審核' | '已完成'
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    notes: str | None = None


@dataclass
class MantisTicket:
    ticket_id: str
    summary: str
    created_time: str | None = None
    company_id: str | None = None
    priority: str | None = None
    status: str | None = None
    issue_type: str | None = None
    module: str | None = None
    handler: str | None = None
    planned_fix: str | None = None
    actual_fix: str | None = None
    progress: str | None = None
    notes: str | None = None           # 原始備註欄位（舊版相容，不再從 SOAP 寫入）
    synced_at: str | None = None
    # ── 新增欄位 ──
    severity: str | None = None
    reporter: str | None = None
    last_updated: str | None = None    # Mantis 最後更新時間
    description: str | None = None
    notes_json: str | None = None      # Mantis Bug 筆記 JSON 陣列（最後 5 條）
    notes_count: int | None = None     # Mantis 筆記總數（用於判斷是否顯示「查看更多」）


@dataclass
class ClassificationRule:
    rule_type: str
    pattern: str
    value: str
    priority: int
    rule_id: int | None = None
    enabled: bool = True
    created_at: str | None = None


@dataclass
class ProcessedFile:
    file_hash: str
    filename: str
    message_id: str | None = None
    processed_at: str | None = None


@dataclass
class Synonym:
    word: str
    synonym: str
    group_name: str
    id: int | None = None


@dataclass
class CaseMantisLink:
    case_id: str
    ticket_id: str
    summary: str | None = None      # 連結摘要說明
    issue_date: str | None = None   # 格式 YYYY/MM/DD，來自主旨 ISSUE_YYYYMMDD_


@dataclass
class CustomColumn:
    """自訂欄位中繼資料 — custom_columns table."""
    col_key: str           # cx_1, cx_2…
    col_label: str         # 中文顯示名稱
    col_order: int         # 建立序號
    visible_in_list: bool = True


@dataclass
class CaseLog:
    """補充記錄 — case_logs table."""
    log_id: str               # LOG-YYYYMMDD-NNN
    case_id: str
    direction: str            # '客戶來信' | 'HCP 信件回覆' | 'HCP 線上回覆' | '內部討論'
    content: str
    mantis_ref: str | None = None   # Mantis Issue 編號（可空）
    logged_by: str | None = None    # 記錄人
    logged_at: str = ""             # YYYY/MM/DD HH:MM:SS
    reply_time: str | None = None   # 回覆時間（YYYY/MM/DD HH:MM）


@dataclass
class Staff:
    """人員資料 — staff table."""
    staff_id: str          # 自動產生：STAFF-YYYYMMDDHHMMSS
    name: str              # 顯示名稱（如 JILL）
    email: str             # 完整 Email（如 jill@ares.com.tw）
    role: str              # 'cs'（客服）| 'sales'（業務）
    phone: str | None = None
    notes: str | None = None
    created_at: str | None = None


@dataclass
class PatchRecord:
    """Patch 整理記錄 — cs_patches table."""
    type: str = "single"          # "single" | "monthly"
    month_str: str | None = None  # "202604"，monthly 專用
    patch_dir: str | None = None
    status: str = "in_progress"   # "in_progress" | "completed"
    patch_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class PatchIssue:
    """Patch Issue 項目 — cs_patch_issues table."""
    patch_id: int | None = None
    issue_no: str = ""
    program_code: str | None = None
    program_name: str | None = None
    issue_type: str = "BugFix"    # "BugFix" | "Enhancement"
    region: str = "共用"           # "TW" | "CN" | "共用"
    description: str | None = None
    impact: str | None = None
    test_direction: str | None = None
    mantis_detail: str | None = None  # JSON 字串
    source: str = "manual"            # "manual" | "mantis"
    sort_order: int = 0
    issue_id: int | None = None
    created_at: str | None = None


@dataclass
class ReleaseKeyword:
    id: int | None = None
    keyword: str = ""
    ktype: str = "confirm"  # 'confirm' | 'ship'
    created_at: str | None = None


@dataclass
class ReleaseItem:
    id: int | None = None
    case_id: str | None = None
    mantis_ticket_id: str | None = None
    assignee: str | None = None
    client_name: str | None = None
    note: str | None = None
    status: str = "待發"      # '待發' | '已發布'
    month_str: str | None = None   # 'YYYYMM'
    patch_id: int | None = None
    created_at: str | None = None
