"""Dashboard view — KPI cards, recent cases, alerts."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.case_manager import CaseManager
from hcp_cms.core.staleness_checker import StalenessChecker
from hcp_cms.data.repositories import CaseRepository
from hcp_cms.ui.theme import ColorPalette, ThemeManager


class KPICard(QFrame):
    """A single KPI metric card."""

    def __init__(self, title: str, value: str, subtitle: str = "", color: str = "#3b82f6") -> None:
        super().__init__()
        self._border_color = color
        self.setFrameStyle(QFrame.Shape.Box)

        layout = QVBoxLayout(self)

        self._title_label = QLabel(title)
        layout.addWidget(self._title_label)

        self._value_label = QLabel(value)
        layout.addWidget(self._value_label)

        self._sub_label: QLabel | None = None
        if subtitle:
            self._sub_label = QLabel(subtitle)
            layout.addWidget(self._sub_label)

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)

    def apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self.setStyleSheet(f"""
            QFrame {{ background-color: {p.bg_secondary}; border-radius: 8px;
                     border-left: 3px solid {self._border_color}; padding: 8px; }}
        """)
        self._title_label.setStyleSheet(f"color: {p.text_muted}; font-size: 11px;")
        self._value_label.setStyleSheet(f"color: {p.text_primary}; font-size: 24px; font-weight: bold;")
        if self._sub_label:
            self._sub_label.setStyleSheet(f"color: {p.success}; font-size: 10px;")


class DashboardView(QWidget):
    """Dashboard with KPI cards and recent cases."""

    def __init__(self, conn: sqlite3.Connection | None = None, theme_mgr: ThemeManager | None = None) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._setup_ui()
        if conn:
            self.refresh()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        self._title = QLabel("📊 儀表板")
        layout.addWidget(self._title)

        # KPI cards grid
        kpi_layout = QGridLayout()
        self._kpi_total = KPICard("本月案件", "0", color="#3b82f6")
        self._kpi_reply_rate = KPICard("回覆率", "0%", color="#10b981")
        self._kpi_pending = KPICard("待處理", "0", color="#f59e0b")
        self._kpi_frt = KPICard("平均 FRT", "---", color="#8b5cf6")

        kpi_layout.addWidget(self._kpi_total, 0, 0)
        kpi_layout.addWidget(self._kpi_reply_rate, 0, 1)
        kpi_layout.addWidget(self._kpi_pending, 0, 2)
        kpi_layout.addWidget(self._kpi_frt, 0, 3)
        layout.addLayout(kpi_layout)

        # 近 3 個月統計表
        self._monthly_label = QLabel("📅 近 3 個月案件統計")
        layout.addWidget(self._monthly_label)

        self._monthly_table = QTableWidget(0, 7)
        self._monthly_table.setHorizontalHeaderLabels(
            ["月份", "總案件", "已回覆", "處理中", "已完成", "回覆率", "平均 FRT"]
        )
        self._monthly_table.horizontalHeader().setStretchLastSection(True)
        self._monthly_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._monthly_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._monthly_table.verticalHeader().setVisible(False)
        self._monthly_table.setMaximumHeight(150)
        layout.addWidget(self._monthly_table)

        # Action 區
        action_row = QHBoxLayout()
        self._staleness_btn = QPushButton("⚠ 警示未結清單")
        self._staleness_btn.setToolTip(
            "找出處理中、超過 48 工作小時無 HCP 回覆的未結案件，"
            "並透過 Exchange 寄送警示通知給 handler。"
        )
        self._staleness_btn.clicked.connect(self._on_check_staleness)
        action_row.addWidget(self._staleness_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Recent cases table
        self._recent_label = QLabel("最近案件")
        layout.addWidget(self._recent_label)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["案件編號", "公司", "主旨", "狀態", "時間"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

    def refresh(self) -> None:
        """Refresh dashboard data from database."""
        if not self._conn:
            return
        try:
            now = datetime.now()
            mgr = CaseManager(self._conn)
            stats = mgr.get_dashboard_stats(now.year, now.month)

            self._kpi_total.set_value(str(stats["total"]))
            self._kpi_reply_rate.set_value(f"{stats['reply_rate']}%")
            self._kpi_pending.set_value(str(stats["pending"]))
            frt = stats.get("avg_frt")
            self._kpi_frt.set_value(f"{frt}h" if frt is not None else "---")

            # 近 3 個月統計表
            monthly = mgr.get_monthly_stats_range(
                months_back=3, ref_year=now.year, ref_month=now.month,
            )
            self._monthly_table.setRowCount(len(monthly))
            for i, m in enumerate(monthly):
                frt_m = m.get("avg_frt")
                self._monthly_table.setItem(i, 0, QTableWidgetItem(m["month"]))
                self._monthly_table.setItem(i, 1, QTableWidgetItem(str(m["total"])))
                self._monthly_table.setItem(i, 2, QTableWidgetItem(str(m["replied"])))
                self._monthly_table.setItem(i, 3, QTableWidgetItem(str(m["pending"])))
                self._monthly_table.setItem(i, 4, QTableWidgetItem(str(m["completed"])))
                self._monthly_table.setItem(i, 5, QTableWidgetItem(f"{m['reply_rate']}%"))
                self._monthly_table.setItem(
                    i, 6, QTableWidgetItem(f"{frt_m}h" if frt_m is not None else "—"),
                )
            self._monthly_table.resizeColumnsToContents()

            # Recent cases
            repo = CaseRepository(self._conn)
            cases = repo.list_by_month(now.year, now.month)[:10]
            self._table.setRowCount(len(cases))
            for i, case in enumerate(cases):
                self._table.setItem(i, 0, QTableWidgetItem(case.case_id))
                self._table.setItem(i, 1, QTableWidgetItem(case.company_id or ""))
                self._table.setItem(i, 2, QTableWidgetItem(case.subject or ""))
                self._table.setItem(i, 3, QTableWidgetItem(case.status))
                self._table.setItem(i, 4, QTableWidgetItem(case.sent_time or ""))
        except Exception:
            pass

    _STALENESS_THRESHOLD_HOURS = 48.0

    def _on_check_staleness(self) -> None:
        """檢查超時案件 → 顯示確認對話框 → 發送 email 提醒。"""
        if not self._conn:
            return

        checker = StalenessChecker(self._conn)
        stale = checker.find_stale_cases(threshold_hours=self._STALENESS_THRESHOLD_HOURS)

        if not stale:
            QMessageBox.information(
                self, "警示未結清單",
                f"目前沒有需警示的未結案件（>{int(self._STALENESS_THRESHOLD_HOURS)} 工作小時無 HCP 回覆）。"
            )
            return

        # 預覽對話框
        from hcp_cms.ui.staleness_dialog import StalenessReminderDialog
        palette = self._theme_mgr.current_palette() if self._theme_mgr else None
        dlg = StalenessReminderDialog(
            stale, self._STALENESS_THRESHOLD_HOURS, parent=self, palette=palette,
        )
        if dlg.exec() != StalenessReminderDialog.DialogCode.Accepted:
            return

        selected = dlg.selected_cases()
        if not selected:
            QMessageBox.information(self, "發送警示", "未勾選任何案件。")
            return

        # 依 handler_email 分組（先算清楚要寄幾封給誰）
        groups: dict[str, list[dict]] = {}
        for c in selected:
            email = c.get("handler_email")
            if not email:
                continue
            groups.setdefault(email, []).append(c)

        if not groups:
            QMessageBox.warning(self, "發送警示", "勾選的案件都沒有 handler email，無法發送。")
            return

        # 二次確認 — 預覽收件人 + 件數，避免誤觸
        preview_lines = [
            f"  • {email}（{len(cases)} 件案件）"
            for email, cases in groups.items()
        ]
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("確認發送警示通知")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(
            f"即將寄出 {len(groups)} 封 email 給以下收件人，涵蓋 {len(selected)} 件案件：\n\n"
            + "\n".join(preview_lines)
            + "\n\n確定要發送嗎？"
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        if msg_box.exec() != QMessageBox.StandardButton.Yes:
            return

        # 連線 Exchange（沿用既有 keyring 帳密）
        from hcp_cms.services.credential import CredentialManager
        from hcp_cms.services.mail.exchange import ExchangeProvider

        creds = CredentialManager()
        server = creds.retrieve("mail_exchange_server") or ""
        user = creds.retrieve("mail_exchange_user") or ""
        pwd = creds.retrieve("mail_exchange_password") or ""
        email_addr = creds.retrieve("mail_exchange_email") or user
        if not all([user, pwd, email_addr]):
            QMessageBox.warning(
                self, "Exchange 設定不完整",
                "請先到「系統設定」填寫 Exchange 帳號／密碼／信箱。"
            )
            return

        provider = ExchangeProvider(server=server, email_address=email_addr)
        provider.set_credentials(user, pwd)
        if not provider.connect():
            QMessageBox.critical(
                self, "Exchange 連線失敗",
                "無法連線 Exchange，請檢查設定與網路。"
            )
            return

        ok = 0
        fail = 0
        for handler_email, cases in groups.items():
            subject, body = self._build_reminder_email(cases)
            if provider.send_email(to=[handler_email], subject=subject, body=body):
                ok += 1
            else:
                fail += 1

        QMessageBox.information(
            self, "警示通知發送完成",
            f"✓ 成功 {ok} 封 / ✗ 失敗 {fail} 封\n"
            f"涵蓋 {len(selected)} 件未結案件"
        )

    @staticmethod
    def _build_reminder_email(cases: list[dict]) -> tuple[str, str]:
        """組裝警示通知 email 的 subject 與 body。"""
        subject = f"[HCP CMS] 警示未結清單：{len(cases)} 件待追蹤"

        lines = [
            f"以下 {len(cases)} 件未結案件已超過 48 工作小時無 HCP 回覆，請追蹤：",
            "",
        ]
        for i, c in enumerate(cases, 1):
            lines.append(f"{i}. {c['case_id']}  {c.get('subject') or ''}")
            lines.append(f"   最後 HCP 回覆：{c['last_hcp_reply']}")
            lines.append(f"   距今工作時數：{c['hours_since_last_reply']:.1f} 小時")
            lines.append("")
        lines.append("—— 由 HCP CMS 自動產生（請勿直接回覆此信）")
        return subject, "\n".join(lines)

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
        self._monthly_label.setStyleSheet(f"color: {p.text_tertiary}; font-weight: bold; margin-top: 16px;")
        self._recent_label.setStyleSheet(f"color: {p.text_tertiary}; font-weight: bold; margin-top: 16px;")
        self._kpi_total.apply_theme(p)
        self._kpi_reply_rate.apply_theme(p)
        self._kpi_pending.apply_theme(p)
        self._kpi_frt.apply_theme(p)
