"""KMS knowledge base view — search, CRUD, 待審核審核。"""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hcp_cms.core.kms_engine import KMSEngine

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})


class TextExpandDialog(QDialog):
    """欄位展開檢視對話框。"""

    def __init__(self, title: str, content: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(content)
        layout.addWidget(text)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class KMSImageViewDialog(QDialog):
    """完整回覆視窗：HTML + 圖片。"""

    def __init__(self, qa, db_dir: Path | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"完整回覆 — {qa.qa_id}")
        self.resize(900, 700)
        self._qa = qa
        self._db_dir = db_dir
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._web = QWebEngineView()
        html = self._build_html()
        if self._db_dir:
            base_url = QUrl.fromLocalFile(str(self._db_dir) + "/")
            self._web.setHtml(html, base_url)
        else:
            self._web.setHtml(html)
        layout.addWidget(self._web, stretch=1)

        # 附件縮圖列
        img_dir = (self._db_dir / "kms_attachments" / self._qa.qa_id) if self._db_dir else None
        if img_dir and img_dir.exists():
            scroll = QScrollArea()
            scroll.setFixedHeight(120)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            thumb_widget = QWidget()
            thumb_layout = QHBoxLayout(thumb_widget)
            for img_path in sorted(img_dir.iterdir()):
                if img_path.suffix.lower() in _IMAGE_EXTS:
                    lbl = QLabel()
                    pix = QPixmap(str(img_path)).scaled(
                        100, 100,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    lbl.setPixmap(pix)
                    lbl.setCursor(Qt.CursorShape.PointingHandCursor)
                    img_path_str = str(img_path)
                    lbl.mousePressEvent = lambda e, p=img_path_str: self._open_full_image(p)
                    thumb_layout.addWidget(lbl)
            thumb_layout.addStretch()
            scroll.setWidget(thumb_widget)
            layout.addWidget(scroll)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _build_html(self) -> str:
        qa = self._qa
        # 嘗試重讀 .msg html_body
        html_body = None
        if qa.doc_name:
            msg_path = Path(qa.doc_name)
            if msg_path.exists():
                from hcp_cms.services.mail.msg_reader import MSGReader
                raw = MSGReader(directory=None).read_single_file(msg_path)
                if raw and raw.html_body:
                    html_body = self._replace_cid(raw.html_body)

        if html_body:
            return html_body

        # fallback：用圖片 + 文字組合簡易 HTML
        img_dir = (self._db_dir / "kms_attachments" / qa.qa_id) if self._db_dir else None
        img_html = ""
        if img_dir and img_dir.exists():
            for img_path in sorted(img_dir.iterdir()):
                if img_path.suffix.lower() in _IMAGE_EXTS:
                    img_html += f'<img src="{img_path.as_uri()}" style="max-width:100%;margin:8px 0;"><br>'

        q = (qa.question or "").replace("<", "&lt;").replace(">", "&gt;")
        a = (qa.answer or "").replace("<", "&lt;").replace(">", "&gt;")
        s = (qa.solution or "").replace("<", "&lt;").replace(">", "&gt;")
        return f"""<html><body style="font-family:sans-serif;padding:16px">
<h3>問題</h3><pre>{q}</pre>
<h3>回覆</h3><pre>{a}</pre>
{img_html}
{'<h3>解決方案</h3><pre>' + s + '</pre>' if s else ''}
</body></html>"""

    def _replace_cid(self, html: str) -> str:
        """將 cid: 圖片參考替換為 file:// 路徑。"""
        if not self._db_dir:
            return html
        img_dir = self._db_dir / "kms_attachments" / self._qa.qa_id
        def replacer(m):
            cid = m.group(1).split("@")[0]
            for f in (img_dir.iterdir() if img_dir.exists() else []):
                if f.stem.lower() == cid.lower() or f.name.lower() == cid.lower():
                    return f'src="{f.as_uri()}"'
            return m.group(0)
        return re.sub(r'src=["\']cid:([^"\'>\s]+)["\']', replacer, html, flags=re.IGNORECASE)

    def _open_full_image(self, img_path_str: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("圖片檢視")
        dlg.resize(800, 600)
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        pix = QPixmap(img_path_str)
        lbl.setPixmap(pix.scaled(
            780, 560,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        lay.addWidget(lbl)
        dlg.exec()


class QAReviewDialog(QDialog):
    """待審核 QA 編輯對話框。"""

    def __init__(self, qa, parent=None) -> None:
        super().__init__(parent)
        self.qa = qa
        self._result_action: str | None = None
        self.setWindowTitle(f"QA 審核編輯 — {qa.qa_id}")
        self.setMinimumWidth(600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._question = QTextEdit(self.qa.question or "")
        self._question.setFixedHeight(80)
        self._answer = QTextEdit(self.qa.answer or "")
        self._answer.setFixedHeight(80)
        self._solution = QTextEdit(self.qa.solution or "")
        self._solution.setFixedHeight(60)
        self._keywords = QLineEdit(self.qa.keywords or "")
        self._product = QLineEdit(self.qa.system_product or "")

        form.addRow("問題：", self._question)
        form.addRow("回覆：", self._answer)
        form.addRow("解決方案：", self._solution)
        form.addRow("關鍵字：", self._keywords)
        form.addRow("產品：", self._product)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        draft_btn = QPushButton("💾 儲存草稿")
        draft_btn.clicked.connect(self._on_draft)
        approve_btn = QPushButton("✅ 確認完成")
        approve_btn.clicked.connect(self._on_approve)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(draft_btn)
        btn_layout.addWidget(approve_btn)
        layout.addLayout(btn_layout)

    def _collect_fields(self) -> dict:
        return {
            "question": self._question.toPlainText().strip(),
            "answer": self._answer.toPlainText().strip(),
            "solution": self._solution.toPlainText().strip() or None,
            "keywords": self._keywords.text().strip() or None,
            "system_product": self._product.text().strip() or None,
        }

    def _on_draft(self) -> None:
        self._result_action = "draft"
        self._result_fields = self._collect_fields()
        self.accept()

    def _on_approve(self) -> None:
        self._result_action = "approve"
        self._result_fields = self._collect_fields()
        self.accept()

    def result_action(self) -> str | None:
        return self._result_action

    def result_fields(self) -> dict:
        return getattr(self, "_result_fields", {})


class KMSView(QWidget):
    """KMS knowledge base page."""

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        kms: KMSEngine | None = None,
        db_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._kms = kms or (KMSEngine(conn) if conn else None)
        self._db_dir = db_dir
        self._results: list = []
        self._pending: list = []
        self._setup_ui()

    def _make_field_widget(self, label: str, attr_name: str) -> tuple[QWidget, QTextEdit]:
        """建立標題列 + 展開按鈕 + QTextEdit 的組合 widget。"""
        wrapper = QWidget()
        vlay = QVBoxLayout(wrapper)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(2)

        header = QWidget()
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        hlay.addWidget(lbl)
        hlay.addStretch()
        expand_btn = QPushButton("⛶")
        expand_btn.setFixedSize(22, 22)
        expand_btn.setToolTip("展開檢視")
        expand_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #64748b; font-size: 14px; border: none; }"
            " QPushButton:hover { color: #e2e8f0; }"
        )
        hlay.addWidget(expand_btn)
        vlay.addWidget(header)

        edit = QTextEdit()
        edit.setReadOnly(True)
        vlay.addWidget(edit)

        field_label = label
        expand_btn.clicked.connect(
            lambda: TextExpandDialog(f"{field_label} — 展開檢視", edit.toPlainText(), self).exec()
        )
        return wrapper, edit

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📚 KMS 知識庫")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f1f5f9;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # ── 全部 tab ──────────────────────────────────────────────────
        all_tab = QWidget()
        all_layout = QVBoxLayout(all_tab)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜尋知識庫（支援同義詞擴展）...")
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input)
        search_btn = QPushButton("🔍 搜尋")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)
        show_all_btn = QPushButton("📋 顯示全部")
        show_all_btn.clicked.connect(self._on_show_all)
        search_layout.addWidget(show_all_btn)
        new_btn = QPushButton("➕ 新增 QA")
        new_btn.clicked.connect(self._on_new_qa)
        search_layout.addWidget(new_btn)
        export_sel_btn = QPushButton("💾 匯出選取")
        export_sel_btn.clicked.connect(self._on_export_selected)
        search_layout.addWidget(export_sel_btn)

        export_all_btn = QPushButton("📄 匯出全部")
        export_all_btn.clicked.connect(self._on_export_all)
        search_layout.addWidget(export_all_btn)
        all_layout.addLayout(search_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["QA 編號", "問題", "產品", "類型", "來源"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._table)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(4, 4, 4, 4)

        # 查看完整回覆按鈕（頂部）
        self._view_btn = QPushButton("🖼️ 查看完整回覆")
        self._view_btn.clicked.connect(self._on_view_full)
        detail_layout.addWidget(self._view_btn)

        # 三個欄位放入垂直 QSplitter
        field_splitter = QSplitter(Qt.Orientation.Vertical)

        q_widget, self._detail_question = self._make_field_widget("問題", "question")
        a_widget, self._detail_answer = self._make_field_widget("回覆", "answer")
        s_widget, self._detail_solution = self._make_field_widget("解決方案", "solution")

        field_splitter.addWidget(q_widget)
        field_splitter.addWidget(a_widget)
        field_splitter.addWidget(s_widget)
        field_splitter.setSizes([200, 400, 200])

        detail_layout.addWidget(field_splitter)

        # 單筆匯出按鈕
        self._export_single_btn = QPushButton("💾 另存 .docx")
        self._export_single_btn.clicked.connect(self._on_export_single)
        detail_layout.addWidget(self._export_single_btn)

        splitter.addWidget(detail)
        all_layout.addWidget(splitter)
        self._tabs.addTab(all_tab, "全部")

        # ── 待審核 tab ────────────────────────────────────────────────
        pending_tab = QWidget()
        pending_layout = QVBoxLayout(pending_tab)

        self._pending_table = QTableWidget(0, 3)
        self._pending_table.setHorizontalHeaderLabels(["QA 編號", "問題預覽", "來源案件"])
        self._pending_table.horizontalHeader().setStretchLastSection(True)
        self._pending_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._pending_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        pending_layout.addWidget(self._pending_table)

        pending_btn_layout = QHBoxLayout()
        review_btn = QPushButton("✏️ 編輯審核")
        review_btn.clicked.connect(self._on_review)
        delete_btn = QPushButton("🗑️ 刪除")
        delete_btn.clicked.connect(self._on_delete_pending)
        pending_btn_layout.addWidget(review_btn)
        pending_btn_layout.addWidget(delete_btn)
        pending_btn_layout.addStretch()
        pending_layout.addLayout(pending_btn_layout)
        self._tabs.addTab(pending_tab, "待審核")

        layout.addWidget(self._tabs)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._refresh_pending()

    def _refresh_pending(self) -> None:
        if not self._kms:
            return
        self._pending = self._kms.list_pending()
        count = len(self._pending)
        self._tabs.setTabText(1, f"待審核{'  🔴' + str(count) if count else ''}")
        self._pending_table.setRowCount(count)
        for i, qa in enumerate(self._pending):
            self._pending_table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._pending_table.setItem(i, 1, QTableWidgetItem((qa.question or "")[:50]))
            self._pending_table.setItem(i, 2, QTableWidgetItem(qa.source_case_id or ""))

    def _on_show_all(self) -> None:
        """載入所有已完成 QA 顯示於全部 tab。"""
        if not self._kms:
            return
        self._results = self._kms.list_approved()
        self._table.setRowCount(len(self._results))
        for i, qa in enumerate(self._results):
            self._table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._table.setItem(i, 1, QTableWidgetItem(qa.question or ""))
            self._table.setItem(i, 2, QTableWidgetItem(qa.system_product or ""))
            self._table.setItem(i, 3, QTableWidgetItem(qa.issue_type or ""))
            self._table.setItem(i, 4, QTableWidgetItem(qa.source or ""))

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query or not self._kms:
            return
        self._results = self._kms.search(query)
        self._table.setRowCount(len(self._results))
        for i, qa in enumerate(self._results):
            self._table.setItem(i, 0, QTableWidgetItem(qa.qa_id))
            self._table.setItem(i, 1, QTableWidgetItem(qa.question or ""))
            self._table.setItem(i, 2, QTableWidgetItem(qa.system_product or ""))
            self._table.setItem(i, 3, QTableWidgetItem(qa.issue_type or ""))
            self._table.setItem(i, 4, QTableWidgetItem(qa.source or ""))

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not self._results:
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._results):
            return
        qa = self._results[row]
        self._detail_question.setPlainText(qa.question or "")
        self._detail_answer.setPlainText(qa.answer or "")
        self._detail_solution.setPlainText(qa.solution or "")
        # 高亮查看按鈕
        if qa.has_image == "是":
            self._view_btn.setStyleSheet("color: #60a5fa;")
        else:
            self._view_btn.setStyleSheet("")

    def _on_new_qa(self) -> None:
        pass  # 預留給新增 QA 對話框

    def _on_review(self) -> None:
        if not self._kms:
            return
        rows = self._pending_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._pending):
            return
        qa = self._pending[row]
        dlg = QAReviewDialog(qa, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dlg.result_fields()
        if dlg.result_action() == "draft":
            self._kms.update_qa(qa.qa_id, **fields)
        elif dlg.result_action() == "approve":
            self._kms.approve_qa(qa.qa_id, **fields)
        self._refresh_pending()

    def _on_delete_pending(self) -> None:
        if not self._kms:
            return
        rows = self._pending_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._pending):
            return
        qa = self._pending[row]
        self._kms.delete_qa(qa.qa_id)
        self._refresh_pending()

    def _on_view_full(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not self._results:
            return
        qa = self._results[rows[0].row()]
        dlg = KMSImageViewDialog(qa, self._db_dir, parent=self)
        dlg.exec()

    def _on_export_single(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not self._results:
            return
        qa = self._results[rows[0].row()]
        self._do_export([qa])

    def _on_export_selected(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        qa_list = [self._results[r.row()] for r in rows if r.row() < len(self._results)]
        self._do_export(qa_list)

    def _on_export_all(self) -> None:
        self._do_export(self._results if self._results else [])

    def _do_export(self, qa_list: list) -> None:
        if not self._kms:
            return
        today = date.today().strftime("%Y%m%d")
        default_name = f"KMS匯出_{today}.docx"
        path, _ = QFileDialog.getSaveFileName(self, "另存 Word 文件", default_name, "Word 文件 (*.docx)")
        if not path:
            return
        try:
            self._kms.export_to_docx(Path(path), db_dir=self._db_dir or Path("."), qa_list=qa_list)
            QMessageBox.information(self, "匯出完成", f"已儲存至：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "匯出失敗", str(e))
