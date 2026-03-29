# 主題系統（深色/淺色模式）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 HCP CMS 建立深色/淺色雙主題系統，支援即時切換、跟隨 Windows 系統、使用者手動覆蓋。

**Architecture:** 建立 `ColorPalette` dataclass 定義語義色彩，`ThemeManager` 管理主題狀態與 Signal 通知。各 View 的 `setStyleSheet()` 改為引用 palette 屬性，透過 `theme_changed` Signal 即時切換。偏好設定存入 `config.json`。

**Tech Stack:** PySide6 Signal/Slot、winreg（Windows 系統偵測）、JSON（設定檔）

---

## 檔案結構

| 動作 | 檔案 | 職責 |
|------|------|------|
| 建立 | `src/hcp_cms/ui/theme.py` | ColorPalette dataclass + ThemeManager |
| 建立 | `tests/unit/test_theme.py` | ThemeManager 單元測試 |
| 修改 | `src/hcp_cms/app.py` | 建立 ThemeManager，傳入 MainWindow |
| 修改 | `src/hcp_cms/ui/main_window.py` | 接收 ThemeManager，全域 QSS 改用 palette |
| 修改 | `src/hcp_cms/ui/settings_view.py` | 新增「外觀」設定區塊 |
| 修改 | `src/hcp_cms/ui/dashboard_view.py` | KPICard + 儀表板樣式改用 palette |
| 修改 | `src/hcp_cms/ui/case_view.py` | 標題樣式改用 palette |
| 修改 | `src/hcp_cms/ui/case_detail_dialog.py` | 詳情面板樣式改用 palette |
| 修改 | `src/hcp_cms/ui/email_view.py` | 連線按鈕 + tab + HTML 預覽改用 palette |
| 修改 | `src/hcp_cms/ui/help_dialog.py` | _DARK_CSS 改為動態生成 |
| 修改 | `src/hcp_cms/ui/kms_view.py` | 標籤 + 智慧查詢樣式改用 palette |
| 修改 | `src/hcp_cms/ui/rules_view.py` | 說明卡片 + 刪除按鈕改用 palette |
| 修改 | `src/hcp_cms/ui/mantis_view.py` | 狀態標籤樣式改用 palette |
| 修改 | `src/hcp_cms/ui/report_view.py` | 標題 + 狀態樣式改用 palette |
| 修改 | `src/hcp_cms/ui/csv_import_dialog.py` | 步驟標籤樣式改用 palette |
| 修改 | `src/hcp_cms/ui/sent_mail_tab.py` | 標題樣式改用 palette |
| 修改 | `src/hcp_cms/ui/widgets/status_bar.py` | 狀態指示器樣式改用 palette |

---

### Task 1: ColorPalette 與常數定義

**Files:**
- Create: `src/hcp_cms/ui/theme.py`
- Create: `tests/unit/test_theme.py`

- [ ] **Step 1: 寫失敗測試 — ColorPalette 結構驗證**

```python
# tests/unit/test_theme.py
"""主題系統單元測試。"""
from __future__ import annotations

import re

from hcp_cms.ui.theme import DARK_PALETTE, LIGHT_PALETTE, ColorPalette


class TestColorPalette:
    """ColorPalette dataclass 結構驗證。"""

    def test_dark_palette_is_color_palette(self) -> None:
        assert isinstance(DARK_PALETTE, ColorPalette)

    def test_light_palette_is_color_palette(self) -> None:
        assert isinstance(LIGHT_PALETTE, ColorPalette)

    def test_all_fields_are_hex_color(self) -> None:
        """所有欄位值必須是 #xxxxxx 格式。"""
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for palette in (DARK_PALETTE, LIGHT_PALETTE):
            for field_name in ColorPalette.__dataclass_fields__:
                value = getattr(palette, field_name)
                assert hex_pattern.match(value), (
                    f"{palette} 的 {field_name} 值 '{value}' 不是有效的 hex 色碼"
                )

    def test_dark_and_light_differ(self) -> None:
        """深色和淺色主題的主背景色必須不同。"""
        assert DARK_PALETTE.bg_primary != LIGHT_PALETTE.bg_primary
        assert DARK_PALETTE.text_primary != LIGHT_PALETTE.text_primary
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_theme.py -v
```
預期：FAIL — `ModuleNotFoundError: No module named 'hcp_cms.ui.theme'`

- [ ] **Step 3: 實作 ColorPalette 與兩組常數**

```python
# src/hcp_cms/ui/theme.py
"""主題系統 — ColorPalette 定義與 ThemeManager。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorPalette:
    """語義化色彩組定義。"""

    # 背景
    bg_primary: str
    bg_secondary: str
    bg_sidebar: str
    bg_code: str
    bg_hover: str

    # 文字
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_muted: str
    text_faint: str

    # 強調色
    accent: str
    accent_button: str
    accent_button_hover: str

    # 邊框
    border_primary: str
    border_secondary: str

    # 狀態色
    success: str
    error: str
    warning: str


DARK_PALETTE = ColorPalette(
    bg_primary="#111827",
    bg_secondary="#1e293b",
    bg_sidebar="#0f172a",
    bg_code="#0f172a",
    bg_hover="#273344",
    text_primary="#f1f5f9",
    text_secondary="#e2e8f0",
    text_tertiary="#94a3b8",
    text_muted="#64748b",
    text_faint="#475569",
    accent="#60a5fa",
    accent_button="#1e40af",
    accent_button_hover="#2563eb",
    border_primary="#334155",
    border_secondary="#1e293b",
    success="#4ade80",
    error="#ef4444",
    warning="#fbbf24",
)

LIGHT_PALETTE = ColorPalette(
    bg_primary="#f8fafc",
    bg_secondary="#ffffff",
    bg_sidebar="#f1f5f9",
    bg_code="#f1f5f9",
    bg_hover="#e2e8f0",
    text_primary="#0f172a",
    text_secondary="#1e293b",
    text_tertiary="#475569",
    text_muted="#64748b",
    text_faint="#94a3b8",
    accent="#2563eb",
    accent_button="#2563eb",
    accent_button_hover="#1d4ed8",
    border_primary="#cbd5e1",
    border_secondary="#e2e8f0",
    success="#16a34a",
    error="#dc2626",
    warning="#d97706",
)
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_theme.py::TestColorPalette -v
```
預期：4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/ui/theme.py tests/unit/test_theme.py
git commit -m "feat: 新增 ColorPalette dataclass 與深色/淺色色彩常數"
```

---

### Task 2: ThemeManager 核心邏輯

**Files:**
- Modify: `src/hcp_cms/ui/theme.py`
- Modify: `tests/unit/test_theme.py`

- [ ] **Step 1: 寫失敗測試 — ThemeManager 基本功能**

在 `tests/unit/test_theme.py` 末尾新增：

```python
import json
from pathlib import Path

from PySide6.QtCore import QObject

from hcp_cms.ui.theme import ThemeManager


class TestThemeManager:
    """ThemeManager 主題管理器測試。"""

    def test_default_mode_is_system(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        assert mgr.current_mode() == "system"

    def test_set_dark(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("dark")
        assert mgr.current_mode() == "dark"
        assert mgr.current_palette() == DARK_PALETTE

    def test_set_light(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("light")
        assert mgr.current_mode() == "light"
        assert mgr.current_palette() == LIGHT_PALETTE

    def test_signal_emitted(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        received: list[ColorPalette] = []
        mgr.theme_changed.connect(received.append)
        mgr.set_theme("light")
        assert len(received) == 1
        assert received[0] == LIGHT_PALETTE

    def test_signal_not_emitted_when_same_mode(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("dark")
        received: list[ColorPalette] = []
        mgr.theme_changed.connect(received.append)
        mgr.set_theme("dark")
        assert len(received) == 0

    def test_save_and_load_config(self, tmp_path: Path) -> None:
        mgr1 = ThemeManager(tmp_path)
        mgr1.set_theme("light")

        mgr2 = ThemeManager(tmp_path)
        assert mgr2.current_mode() == "light"

    def test_invalid_config_falls_back_to_system(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json", encoding="utf-8")
        mgr = ThemeManager(tmp_path)
        assert mgr.current_mode() == "system"

    def test_missing_config_creates_default(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        config_path = tmp_path / "config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["theme"] == "system"

    def test_invalid_mode_ignored(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("dark")
        mgr.set_theme("invalid_mode")
        assert mgr.current_mode() == "dark"
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_theme.py::TestThemeManager -v
```
預期：FAIL — `ImportError: cannot import name 'ThemeManager'`

- [ ] **Step 3: 實作 ThemeManager**

在 `src/hcp_cms/ui/theme.py` 末尾新增：

```python
import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class ThemeManager(QObject):
    """主題管理器 — 管理深色/淺色切換、設定持久化、系統偵測。"""

    theme_changed = Signal(ColorPalette)

    _VALID_MODES = ("dark", "light", "system")

    def __init__(self, config_dir: Path) -> None:
        super().__init__()
        self._config_path = config_dir / "config.json"
        self._mode: str = "system"
        self._palette: ColorPalette = DARK_PALETTE
        self._load_config()
        self._resolve_palette()

    def current_mode(self) -> str:
        """取得當前模式字串。"""
        return self._mode

    def current_palette(self) -> ColorPalette:
        """取得當前色彩組。"""
        return self._palette

    def set_theme(self, mode: str) -> None:
        """切換主題模式。無效值會被忽略。"""
        if mode not in self._VALID_MODES:
            return
        if mode == self._mode:
            return
        self._mode = mode
        self._resolve_palette()
        self._save_config()
        self.theme_changed.emit(self._palette)

    def refresh_system_theme(self) -> None:
        """重新偵測系統主題（僅在 mode='system' 時有效）。"""
        if self._mode != "system":
            return
        old_palette = self._palette
        self._resolve_palette()
        if self._palette != old_palette:
            self.theme_changed.emit(self._palette)

    def _resolve_palette(self) -> None:
        """根據當前模式決定使用哪組色彩。"""
        if self._mode == "light":
            self._palette = LIGHT_PALETTE
        elif self._mode == "dark":
            self._palette = DARK_PALETTE
        else:
            self._palette = (
                LIGHT_PALETTE
                if self._detect_system_light()
                else DARK_PALETTE
            )

    def _detect_system_light(self) -> bool:
        """偵測 Windows 系統是否為淺色模式。"""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 1
        except Exception:
            return False

    def _load_config(self) -> None:
        """從 config.json 載入偏好。"""
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
            mode = data.get("theme", "system")
            if mode in self._VALID_MODES:
                self._mode = mode
            else:
                self._mode = "system"
        except Exception:
            self._mode = "system"
        self._save_config()

    def _save_config(self) -> None:
        """儲存偏好到 config.json。"""
        data = {"theme": self._mode}
        self._config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 4: 執行測試確認通過**

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_theme.py -v
```
預期：全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/ui/theme.py tests/unit/test_theme.py
git commit -m "feat: 新增 ThemeManager — 主題切換、Signal 通知、config.json 持久化"
```

---

### Task 3: app.py 整合 ThemeManager

**Files:**
- Modify: `src/hcp_cms/app.py:29-53`
- Modify: `src/hcp_cms/ui/main_window.py:1-50`

- [ ] **Step 1: 修改 app.py — 建立 ThemeManager 並傳入 MainWindow**

```python
# src/hcp_cms/app.py — 完整 main() 函式
def main() -> int:
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("HCP CMS")
    app.setApplicationVersion(__version__)

    # Initialize i18n
    load_language("zh_TW")

    # Initialize database
    db_path = get_default_db_path()
    db = DatabaseManager(db_path)
    db.initialize()

    # Initialize theme
    from hcp_cms.ui.theme import ThemeManager

    theme_mgr = ThemeManager(db_path.parent)

    # Create and show main window
    window = MainWindow(db.connection, db_dir=db_path.parent, theme_mgr=theme_mgr)
    window.show()

    # Run application
    result = app.exec()

    # Cleanup
    db.close()

    return result
```

- [ ] **Step 2: 修改 MainWindow.__init__ 簽章 — 接收 ThemeManager**

```python
# src/hcp_cms/ui/main_window.py — 修改 import 區塊，新增：
from hcp_cms.ui.theme import ColorPalette, ThemeManager

# 修改 __init__ 簽章：
class MainWindow(QMainWindow):
    """HCP CMS main application window."""

    def __init__(
        self,
        db_connection: sqlite3.Connection | None = None,
        db_dir: Path | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = db_connection
        self._db_dir = db_dir
        self._theme_mgr = theme_mgr
        self.setWindowTitle("HCP CMS v2.0")
        self.setMinimumSize(1200, 800)

        self._setup_ui()
        self._setup_shortcuts()

        # 套用主題
        if self._theme_mgr:
            self._apply_theme(self._theme_mgr.current_palette())
            self._theme_mgr.theme_changed.connect(self._apply_theme)
        else:
            self._apply_dark_theme()
```

- [ ] **Step 3: 執行應用程式確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：所有既有測試 PASSED

- [ ] **Step 4: Commit**

```bash
git add src/hcp_cms/app.py src/hcp_cms/ui/main_window.py
git commit -m "feat: app.py 建立 ThemeManager 並傳入 MainWindow"
```

---

### Task 4: MainWindow 全域 QSS 改用 palette

**Files:**
- Modify: `src/hcp_cms/ui/main_window.py:228-262`

- [ ] **Step 1: 新增 _apply_theme 方法，取代 _apply_dark_theme**

在 `main_window.py` 中新增 `_apply_theme` 方法，將所有硬編碼色碼改為引用 `ColorPalette`：

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """Apply theme stylesheet using the given palette."""
    self.setStyleSheet(f"""
        QMainWindow {{ background-color: {p.bg_primary}; }}
        #sidebar {{ background-color: {p.bg_sidebar}; border-right: 1px solid {p.border_secondary}; }}
        #logo {{ color: {p.accent}; font-size: 16px; font-weight: bold;
                background-color: {p.bg_sidebar}; border-bottom: 1px solid {p.border_secondary}; }}
        #navList {{ background-color: {p.bg_sidebar}; border: none; color: {p.text_tertiary};
                   font-size: 13px; outline: none; }}
        #navList::item {{ padding: 10px 16px; border-radius: 6px; margin: 2px 8px; }}
        #navList::item:selected {{ background-color: {p.accent_button}; color: {p.accent}; }}
        #navList::item:hover {{ background-color: {p.bg_secondary}; }}
        QStackedWidget {{ background-color: {p.bg_primary}; }}
        QLabel {{ color: {p.text_secondary}; }}
        QLineEdit {{ background-color: {p.bg_secondary}; color: {p.text_secondary}; border: 1px solid {p.border_primary};
                    border-radius: 4px; padding: 6px; }}
        QPushButton {{ background-color: {p.accent_button}; color: white; border: none;
                      border-radius: 4px; padding: 8px 16px; font-weight: bold; }}
        QPushButton:hover {{ background-color: {p.accent_button_hover}; }}
        QTableWidget {{ background-color: {p.bg_secondary}; color: {p.text_secondary};
                      gridline-color: {p.border_primary}; border: none; }}
        QTableWidget::item {{ padding: 4px; }}
        QHeaderView::section {{ background-color: {p.accent_button}; color: white;
                               padding: 6px; border: 1px solid {p.border_primary}; }}
        QStatusBar {{ background-color: {p.bg_sidebar}; color: {p.text_muted}; }}
        QComboBox {{ background-color: {p.bg_secondary}; color: {p.text_secondary}; border: 1px solid {p.border_primary};
                   border-radius: 4px; padding: 4px; }}
        QSpinBox {{ background-color: {p.bg_secondary}; color: {p.text_secondary}; border: 1px solid {p.border_primary}; }}
        QTextEdit {{ background-color: {p.bg_secondary}; color: {p.text_secondary}; border: 1px solid {p.border_primary}; }}
        QGroupBox {{ color: {p.text_tertiary}; border: 1px solid {p.border_primary}; border-radius: 6px;
                   margin-top: 8px; padding-top: 16px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
        #navItemLabel {{ color: {p.text_tertiary}; font-size: 13px; background: transparent; }}
        #navShortcutHint {{ color: {p.text_faint}; font-size: 10px; background: transparent; }}
    """)
    # 刷新導覽列選中狀態的顏色
    self._on_nav_changed(self._nav_list.currentRow())
    # 傳播主題給不透過 Signal 連接的元件
    self._current_palette = p
```

- [ ] **Step 2: 修改 _on_nav_changed 中的硬編碼色碼**

```python
def _on_nav_changed(self, index: int) -> None:
    """Switch content view when navigation changes."""
    if 0 <= index < self._stack.count():
        self._stack.setCurrentIndex(index)
    # Update nav label colours to reflect selection
    p = getattr(self, "_current_palette", None)
    selected_color = p.accent if p else "#60a5fa"
    unselected_color = p.text_tertiary if p else "#94a3b8"
    for i in range(self._nav_list.count()):
        widget = self._nav_list.itemWidget(self._nav_list.item(i))
        if widget:
            label = widget.findChild(QLabel, "navItemLabel")
            if label:
                label.setStyleSheet(
                    f"color: {selected_color};" if i == index else f"color: {unselected_color};"
                )
    # 切到信件處理頁時自動連線
    if index == 3:
        self._views["email"].try_auto_connect()
```

- [ ] **Step 3: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 4: Commit**

```bash
git add src/hcp_cms/ui/main_window.py
git commit -m "feat: MainWindow 全域 QSS 改用 ColorPalette 語義色彩"
```

---

### Task 5: MainWindow 系統主題跟隨（ActivationChange）

**Files:**
- Modify: `src/hcp_cms/ui/main_window.py`

- [ ] **Step 1: 新增 changeEvent 處理**

在 `MainWindow` 中新增：

```python
from PySide6.QtCore import QEvent

def changeEvent(self, event: QEvent) -> None:
    """偵測視窗啟用事件，重新檢查系統主題。"""
    if (
        event.type() == QEvent.Type.ActivationChange
        and self.isActiveWindow()
        and self._theme_mgr
    ):
        self._theme_mgr.refresh_system_theme()
    super().changeEvent(event)
```

- [ ] **Step 2: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 3: Commit**

```bash
git add src/hcp_cms/ui/main_window.py
git commit -m "feat: MainWindow 視窗啟用時自動偵測系統主題變更"
```

---

### Task 6: 各 View 傳遞 ThemeManager

**Files:**
- Modify: `src/hcp_cms/ui/main_window.py:100-115`（View 建構）
- Modify: `src/hcp_cms/ui/dashboard_view.py`（簽章）
- Modify: `src/hcp_cms/ui/case_view.py`（簽章）
- Modify: `src/hcp_cms/ui/kms_view.py`（簽章）
- Modify: `src/hcp_cms/ui/email_view.py`（簽章）
- Modify: `src/hcp_cms/ui/mantis_view.py`（簽章）
- Modify: `src/hcp_cms/ui/report_view.py`（簽章）
- Modify: `src/hcp_cms/ui/rules_view.py`（簽章）
- Modify: `src/hcp_cms/ui/settings_view.py`（簽章）

- [ ] **Step 1: 修改所有 View 的 __init__ 簽章，接收 theme_mgr**

每個 View 統一增加 `theme_mgr: ThemeManager | None = None` 參數，在 `__init__` 中儲存並連接 Signal：

```python
# 以 DashboardView 為例，其他 View 同理：
from hcp_cms.ui.theme import ColorPalette, ThemeManager

class DashboardView(QWidget):
    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._theme_mgr = theme_mgr
        self._setup_ui()
        if theme_mgr:
            self._apply_theme(theme_mgr.current_palette())
            theme_mgr.theme_changed.connect(self._apply_theme)
        if conn:
            self.refresh()

    def _apply_theme(self, p: ColorPalette) -> None:
        """套用主題色彩。"""
        pass  # Task 7-13 中逐步實作
```

每個 View 都加上相同模式。`_apply_theme` 先留空（`pass`），後續 Task 逐一填入。

- [ ] **Step 2: 修改 MainWindow._setup_ui 中的 View 建構，傳入 theme_mgr**

```python
self._views: dict[str, QWidget] = {
    "dashboard": DashboardView(self._conn, theme_mgr=self._theme_mgr),
    "cases": CaseView(self._conn, db_path=self._db_dir / "cs_tracker.db" if self._db_dir else None, theme_mgr=self._theme_mgr),
    "kms": KMSView(self._conn, kms=kms, db_dir=self._db_dir, theme_mgr=self._theme_mgr),
    "email": EmailView(self._conn, kms=kms, theme_mgr=self._theme_mgr),
    "mantis": MantisView(self._conn, theme_mgr=self._theme_mgr),
    "reports": ReportView(self._conn, theme_mgr=self._theme_mgr),
    "rules": RulesView(self._conn, theme_mgr=self._theme_mgr),
    "settings": SettingsView(self._conn, theme_mgr=self._theme_mgr),
}
```

各 View 的 `__init__` 簽章需更新：

**CaseView:**
```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    db_path: Path | None = None,
    theme_mgr: ThemeManager | None = None,
) -> None:
```

**KMSView:**
```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    kms: KMSEngine | None = None,
    db_dir: Path | None = None,
    theme_mgr: ThemeManager | None = None,
) -> None:
```

**EmailView:**
```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    kms: KMSEngine | None = None,
    theme_mgr: ThemeManager | None = None,
) -> None:
```

**MantisView:**
```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    theme_mgr: ThemeManager | None = None,
) -> None:
```

**ReportView:**
```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    theme_mgr: ThemeManager | None = None,
) -> None:
```

**RulesView:**
```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    theme_mgr: ThemeManager | None = None,
) -> None:
```

**SettingsView:**
```python
def __init__(
    self,
    conn: sqlite3.Connection | None = None,
    theme_mgr: ThemeManager | None = None,
) -> None:
```

每個都在 `__init__` 裡加上：
```python
self._theme_mgr = theme_mgr
# ... 原有的 _setup_ui() 等 ...
if theme_mgr:
    self._apply_theme(theme_mgr.current_palette())
    theme_mgr.theme_changed.connect(self._apply_theme)
```

- [ ] **Step 3: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 4: Commit**

```bash
git add src/hcp_cms/ui/main_window.py src/hcp_cms/ui/dashboard_view.py src/hcp_cms/ui/case_view.py src/hcp_cms/ui/kms_view.py src/hcp_cms/ui/email_view.py src/hcp_cms/ui/mantis_view.py src/hcp_cms/ui/report_view.py src/hcp_cms/ui/rules_view.py src/hcp_cms/ui/settings_view.py
git commit -m "feat: 所有 View 接收 ThemeManager 並連接 theme_changed Signal"
```

---

### Task 7: DashboardView 主題化

**Files:**
- Modify: `src/hcp_cms/ui/dashboard_view.py`

- [ ] **Step 1: 改造 KPICard 接收 palette**

```python
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
```

- [ ] **Step 2: 實作 DashboardView._apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
    self._recent_label.setStyleSheet(f"color: {p.text_tertiary}; font-weight: bold; margin-top: 16px;")
    self._kpi_total.apply_theme(p)
    self._kpi_reply_rate.apply_theme(p)
    self._kpi_pending.apply_theme(p)
    self._kpi_frt.apply_theme(p)
```

需要將 `_setup_ui` 中的 `title` 和 `recent_label` 存為實例變數 `self._title` 和 `self._recent_label`。

- [ ] **Step 3: 從 _setup_ui 移除硬編碼樣式**

將 `_setup_ui` 中的 `setStyleSheet` 呼叫移除（改由 `_apply_theme` 統一處理）。原本在建構子中設定的樣式字串刪除。

- [ ] **Step 4: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/ui/dashboard_view.py
git commit -m "feat: DashboardView + KPICard 改用 ColorPalette 主題色彩"
```

---

### Task 8: EmailView 主題化（含 HTML 預覽）

**Files:**
- Modify: `src/hcp_cms/ui/email_view.py`

- [ ] **Step 1: 將 _BASE_STYLE 改為動態方法**

```python
def _build_base_style(self, p: ColorPalette) -> str:
    """根據當前主題生成 HTML 預覽 CSS。"""
    return (
        f"body{{margin:16px;font-family:'Segoe UI',Arial,sans-serif;"
        f"font-size:13px;background:{p.bg_secondary};color:{p.text_secondary};line-height:1.6;}}"
        f"pre{{white-space:pre-wrap;word-break:break-word;}}"
        f"a{{color:{p.accent};}}"
        f"blockquote{{border-left:3px solid {p.border_primary};margin:0;padding-left:12px;color:{p.text_tertiary};}}"
        f"img{{max-width:100%;}}"
    )
```

- [ ] **Step 2: 實作 _apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
    self._tab_widget.setStyleSheet(
        f"QTabWidget::pane {{ border: none; background: transparent; }}"
        f"QTabBar::tab {{ background: {p.bg_secondary}; color: {p.text_tertiary};"
        f"  padding: 6px 16px; border-bottom: 2px solid transparent; }}"
        f"QTabBar::tab:selected {{ background: {p.bg_secondary}; color: {p.text_primary};"
        f"  border-bottom: 2px solid #3b82f6; }}"
        f"QTabBar::tab:hover:!selected {{ background: {p.bg_hover}; color: {p.text_secondary}; }}"
    )
    self._update_conn_toggle()
    # 刷新 HTML 預覽
    self._current_palette = p
```

- [ ] **Step 3: 修改 _update_conn_toggle 使用 palette**

```python
def _update_conn_toggle(self) -> None:
    """更新折疊按鈕文字與樣式。"""
    p = getattr(self, "_current_palette", None) or DARK_PALETTE
    arrow = "▲" if self._conn_content.isVisible() else "▼"
    if self._connected_proto:
        self._conn_toggle_btn.setText(f"✅ {self._connected_proto}  {self._connected_user}  {arrow}")
        self._conn_toggle_btn.setStyleSheet(
            f"QPushButton {{ text-align: left; padding: 6px 12px;"
            f" background: {p.bg_secondary}; color: {p.success};"
            f" border: 1px solid #166534; border-radius: 6px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {p.bg_hover}; }}"
        )
    else:
        self._conn_toggle_btn.setText(f"⚙ 連線設定  {arrow}")
        self._conn_toggle_btn.setStyleSheet(
            f"QPushButton {{ text-align: left; padding: 6px 12px;"
            f" background: {p.bg_secondary}; color: {p.text_tertiary};"
            f" border: 1px solid {p.border_primary}; border-radius: 6px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {p.bg_hover}; color: {p.text_secondary}; }}"
        )
```

- [ ] **Step 4: 修改 HTML 渲染處使用動態 CSS**

所有使用 `_BASE_STYLE` 的地方改為呼叫 `self._build_base_style(self._current_palette)`。需要將 `title` 存為 `self._title`。

- [ ] **Step 5: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/email_view.py
git commit -m "feat: EmailView 主題化 — 連線按鈕、tab、HTML 預覽改用 palette"
```

---

### Task 9: HelpDialog 主題化

**Files:**
- Modify: `src/hcp_cms/ui/help_dialog.py`

- [ ] **Step 1: 將 _DARK_CSS 改為函式**

```python
def _build_help_css(p: ColorPalette) -> str:
    """根據主題生成說明對話框 CSS。"""
    # 偶數行背景色：取 bg_primary 和 bg_secondary 之間的中間值
    even_row_bg = p.bg_hover
    return f"""
<style>
body {{
    background-color: {p.bg_secondary};
    color: {p.text_secondary};
    font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    padding: 16px;
}}
h2, h3, h4 {{ color: {p.accent}; margin-top: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th {{ background-color: {p.accent_button}; color: {p.text_primary}; padding: 8px 12px;
     text-align: left; border: 1px solid {p.border_primary}; }}
td {{ padding: 8px 12px; border: 1px solid {p.border_primary}; }}
tr:nth-child(even) {{ background-color: {even_row_bg}; }}
code {{ background-color: {p.bg_code}; color: {p.accent}; padding: 2px 6px;
       border-radius: 4px; font-size: 13px; }}
pre {{ background-color: {p.bg_code}; padding: 12px; border-radius: 6px;
      overflow-x: auto; }}
pre code {{ padding: 0; }}
blockquote {{ border-left: 3px solid {p.accent}; padding-left: 12px;
             color: {p.text_tertiary}; margin: 12px 0; }}
a {{ color: {p.accent}; }}
hr {{ border: none; border-top: 1px solid {p.border_primary}; margin: 20px 0; }}
</style>
"""
```

- [ ] **Step 2: 修改 render_help_html 接收 palette**

```python
def render_help_html(md_text: str, palette: ColorPalette | None = None) -> str:
    """Convert markdown to styled HTML with theme."""
    from hcp_cms.ui.theme import DARK_PALETTE

    p = palette or DARK_PALETTE
    css = _build_help_css(p)
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return f"<html><head>{css}</head><body>{body}</body></html>"
```

- [ ] **Step 3: 修改 HelpDialog 接收 palette 並套用主題**

```python
class HelpDialog(QDialog):
    def __init__(
        self,
        page_index: int,
        manual_text: str,
        parent: object | None = None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        from hcp_cms.ui.theme import DARK_PALETTE

        p = palette or DARK_PALETTE

        # ... 現有的 title / resize 邏輯 ...

        section_md = extract_section(manual_text, page_index)
        html = render_help_html(section_md, palette=p)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setHtml(html)
        layout.addWidget(self._browser)

        close_btn = QPushButton("關閉")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet(
            f"QPushButton {{ background-color: {p.border_primary}; color: {p.text_secondary}; "
            f"border: 1px solid {p.text_faint}; border-radius: 4px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {p.text_faint}; }}"
        )
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet(f"QDialog {{ background-color: {p.bg_secondary}; }}")
```

- [ ] **Step 4: 修改 MainWindow._on_help_requested 傳入 palette**

```python
def _on_help_requested(self) -> None:
    from hcp_cms.ui.help_dialog import HelpDialog

    manual_text = self._load_manual()
    if manual_text:
        page_index = self._nav_list.currentRow()
        palette = self._current_palette if hasattr(self, "_current_palette") else None
        dialog = HelpDialog(page_index, manual_text, parent=self, palette=palette)
        dialog.exec()
```

- [ ] **Step 5: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/help_dialog.py src/hcp_cms/ui/main_window.py
git commit -m "feat: HelpDialog 主題化 — CSS 動態生成、接收 palette"
```

---

### Task 10: CaseView + CaseDetailDialog 主題化

**Files:**
- Modify: `src/hcp_cms/ui/case_view.py`
- Modify: `src/hcp_cms/ui/case_detail_dialog.py`

- [ ] **Step 1: CaseView._apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
```

需要將 `_setup_ui` 中的 `title` 存為 `self._title`。

- [ ] **Step 2: CaseDetailDialog 主題化**

CaseDetailDialog 不直接連接 ThemeManager（它是一個短命 Dialog），改為在建構時接收 `palette`：

```python
class CaseDetailDialog(QDialog):
    case_updated = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        case_id: str,
        parent: QWidget | None = None,
        palette: ColorPalette | None = None,
    ) -> None:
        super().__init__(parent)
        from hcp_cms.ui.theme import DARK_PALETTE

        self._palette = palette or DARK_PALETTE
        # ... 其餘不變 ...
```

在 `_build_tab3` 和 `_setup_detail_panel` 等方法中，將硬編碼色碼替換為 `self._palette` 引用：

```python
# 詳情面板
detail_frame.setStyleSheet(
    f"QFrame {{ background-color: {self._palette.bg_secondary}; "
    f"border: 1px solid {self._palette.border_primary}; border-radius: 6px; }}"
)
self._detail_title.setStyleSheet(f"color: {self._palette.text_faint}; font-size: 12px;")

# Grid 標籤
lbl.setStyleSheet(f"color: {self._palette.text_muted}; font-size: 10px;")
val.setStyleSheet(f"color: {self._palette.text_secondary}; font-size: 11px;")

# 問題描述 / Bug 筆記
self._detail_desc.setStyleSheet(
    f"QTextEdit {{ background: {self._palette.bg_code}; color: {self._palette.text_tertiary}; border: none; font-size: 11px; }}"
)
self._detail_notes.setStyleSheet(
    f"QTextEdit {{ background: {self._palette.bg_code}; color: {self._palette.text_tertiary}; border: none; font-size: 11px; }}"
)

# 連結
self._detail_more_link.setStyleSheet(f"color: {self._palette.accent}; font-size: 11px;")
```

- [ ] **Step 3: CaseView 開啟 Dialog 時傳入 palette**

在 CaseView 中所有建立 `CaseDetailDialog` 的地方，加上 `palette=self._theme_mgr.current_palette() if self._theme_mgr else None`。

- [ ] **Step 4: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/ui/case_view.py src/hcp_cms/ui/case_detail_dialog.py
git commit -m "feat: CaseView + CaseDetailDialog 主題化"
```

---

### Task 11: KMSView + RulesView + MantisView 主題化

**Files:**
- Modify: `src/hcp_cms/ui/kms_view.py`
- Modify: `src/hcp_cms/ui/rules_view.py`
- Modify: `src/hcp_cms/ui/mantis_view.py`

- [ ] **Step 1: KMSView._apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
    self._smart_desc.setStyleSheet(f"color: {p.text_tertiary}; padding: 4px 0;")
    self._smart_result_label.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px;")
    self._answer_label.setStyleSheet(f"color: {p.accent}; font-weight: bold;")
    self._smart_answer_box.setStyleSheet(
        f"background: {p.bg_secondary}; color: {p.text_primary}; "
        f"border: 1px solid {p.border_primary}; border-radius: 4px;"
    )
```

需要將 `_setup_ui` 中相關的 label 存為實例變數。

- [ ] **Step 2: RulesView._apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
    self._desc_card.setStyleSheet(
        f"QFrame {{ background-color: {p.bg_secondary}; border: 1px solid {p.border_primary};"
        f" border-radius: 6px; padding: 4px; }}"
    )
    self._desc_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {p.accent};")
    self._desc_body.setStyleSheet(f"font-size: 12px; color: {p.text_secondary};")
    self._desc_default.setStyleSheet(f"font-size: 11px; color: {p.text_muted}; font-style: italic;")
    self._delete_btn.setStyleSheet(f"background-color: {p.error};")
```

需要將 `_setup_ui` 中的 `title` 存為 `self._title`。

- [ ] **Step 3: MantisView._apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
    self._url_label.setStyleSheet(f"color: {p.text_tertiary};")
```

需要將 `_setup_ui` 中的 `title` 存為 `self._title`。動態狀態標籤（`_status_label`）的色彩是語義性的（紅=錯誤、黃=進行中、綠=成功），不隨主題改變。

- [ ] **Step 4: 從各檔案 _setup_ui 移除硬編碼樣式**

將所有在 `_setup_ui` 中直接設定的色碼樣式移除，由 `_apply_theme` 統一管理。

- [ ] **Step 5: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/hcp_cms/ui/kms_view.py src/hcp_cms/ui/rules_view.py src/hcp_cms/ui/mantis_view.py
git commit -m "feat: KMSView + RulesView + MantisView 主題化"
```

---

### Task 12: 剩餘 View 主題化（ReportView、CsvImportDialog、SentMailTab、StatusWidget、SettingsView、DeleteCasesDialog）

**Files:**
- Modify: `src/hcp_cms/ui/report_view.py`
- Modify: `src/hcp_cms/ui/csv_import_dialog.py`
- Modify: `src/hcp_cms/ui/sent_mail_tab.py`
- Modify: `src/hcp_cms/ui/widgets/status_bar.py`
- Modify: `src/hcp_cms/ui/settings_view.py`
- Modify: `src/hcp_cms/ui/delete_cases_dialog.py`

- [ ] **Step 1: ReportView._apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
    self._status.setStyleSheet(f"color: {p.text_muted};")
```

需要將 `title` 和 `self._status` 中的硬編碼色碼移除。

- [ ] **Step 2: SettingsView._apply_theme**

```python
def _apply_theme(self, p: ColorPalette) -> None:
    """套用主題色彩。"""
    self._title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p.text_primary};")
    self._url_hint.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px;")
    self._exch_server_hint.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px;")
    self._notice.setStyleSheet(
        f"QFrame#migrationNotice {{ background-color: {p.warning}22; border-radius: 6px; padding: 8px; }}"
    )
    self._notice_lbl.setStyleSheet(f"color: {p.warning}; font-size: 12px;")
```

需要將 `title`、`url_hint`、`exch_server_hint`、`notice`、`notice_lbl` 存為實例變數。

注意：移機提醒區塊在淺色/深色下都需要可讀的配色。使用 `warning` 色搭配透明度背景。

- [ ] **Step 3: CsvImportDialog — 短命 Dialog，建構時接收 palette**

```python
class CsvImportDialog(QDialog):
    def __init__(
        self,
        conn: sqlite3.Connection,
        parent=None,
        palette: ColorPalette | None = None,
    ) -> None:
        # ...
        from hcp_cms.ui.theme import DARK_PALETTE
        self._palette = palette or DARK_PALETTE
```

套用：
```python
self._step_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {self._palette.text_primary};")
self._file_label.setStyleSheet(f"color: {self._palette.text_tertiary};")
```

- [ ] **Step 4: SentMailTab — 接收 theme_mgr**

```python
class SentMailTab(QWidget):
    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        theme_mgr: ThemeManager | None = None,
    ) -> None:
        # ...
        self._theme_mgr = theme_mgr

    def _apply_theme(self, p: ColorPalette) -> None:
        self._summary_label.setStyleSheet(f"font-weight: bold; color: {p.text_primary};")
        self._list_label.setStyleSheet(f"font-weight: bold; color: {p.text_primary};")
```

EmailView 建構 SentMailTab 時傳入 `theme_mgr`。

- [ ] **Step 5: StatusWidget — 接收 theme_mgr**

```python
class StatusWidget(QWidget):
    def __init__(self, theme_mgr: ThemeManager | None = None) -> None:
        super().__init__()
        self._theme_mgr = theme_mgr
        # ... layout setup ...

    def set_db_connected(self, connected: bool) -> None:
        if connected:
            self._db_status.setText("🟢 DB 已連線")
            self._db_status.setStyleSheet(f"color: #34d399; font-size: 11px;")
        else:
            self._db_status.setText("🔴 DB 未連線")
            self._db_status.setStyleSheet(f"color: #ef4444; font-size: 11px;")
```

StatusWidget 的狀態色（綠=連線、紅=斷線）是語義性的，不隨主題改變。

- [ ] **Step 6: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 7: Commit**

```bash
git add src/hcp_cms/ui/report_view.py src/hcp_cms/ui/csv_import_dialog.py src/hcp_cms/ui/sent_mail_tab.py src/hcp_cms/ui/widgets/status_bar.py src/hcp_cms/ui/settings_view.py src/hcp_cms/ui/delete_cases_dialog.py
git commit -m "feat: 剩餘 View/Dialog 主題化 — ReportView、CsvImport、SentMailTab、StatusWidget、Settings"
```

---

### Task 13: SettingsView 新增「外觀」主題切換 UI

**Files:**
- Modify: `src/hcp_cms/ui/settings_view.py`

- [ ] **Step 1: 在 _setup_ui 的標題下方新增「外觀」區塊**

在 `layout.addWidget(title)` 之後、`user_group` 之前插入：

```python
# 外觀設定
appearance_group = QGroupBox("外觀")
appearance_layout = QHBoxLayout(appearance_group)
appearance_layout.addWidget(QLabel("主題模式："))

from PySide6.QtWidgets import QRadioButton, QButtonGroup

self._theme_system = QRadioButton("跟隨系統")
self._theme_dark = QRadioButton("深色")
self._theme_light = QRadioButton("淺色")

self._theme_group = QButtonGroup(self)
self._theme_group.addButton(self._theme_system, 0)
self._theme_group.addButton(self._theme_dark, 1)
self._theme_group.addButton(self._theme_light, 2)

appearance_layout.addWidget(self._theme_system)
appearance_layout.addWidget(self._theme_dark)
appearance_layout.addWidget(self._theme_light)
appearance_layout.addStretch()

# 根據當前模式設定選中狀態
if self._theme_mgr:
    mode = self._theme_mgr.current_mode()
    if mode == "system":
        self._theme_system.setChecked(True)
    elif mode == "dark":
        self._theme_dark.setChecked(True)
    else:
        self._theme_light.setChecked(True)
else:
    self._theme_system.setChecked(True)

self._theme_group.idClicked.connect(self._on_theme_changed)
layout.addWidget(appearance_group)
```

- [ ] **Step 2: 新增 _on_theme_changed Slot**

```python
def _on_theme_changed(self, button_id: int) -> None:
    """使用者切換主題模式。"""
    if not self._theme_mgr:
        return
    mode_map = {0: "system", 1: "dark", 2: "light"}
    mode = mode_map.get(button_id, "system")
    self._theme_mgr.set_theme(mode)
```

- [ ] **Step 3: 執行應用程式手動驗證**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

驗證項目：
1. 設定頁面出現「外觀」區塊，三個 RadioButton
2. 點選「淺色」→ 整個應用程式即時切換為淺色主題
3. 點選「深色」→ 切回深色
4. 點選「跟隨系統」→ 依 Windows 設定自動選擇
5. 重新啟動應用程式 → 主題偏好保持

- [ ] **Step 4: 執行測試確認無回歸**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
```
預期：全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/hcp_cms/ui/settings_view.py
git commit -m "feat: 設定頁面新增「外觀」主題切換 — 跟隨系統/深色/淺色"
```

---

### Task 14: 清理舊的 _apply_dark_theme 並最終驗證

**Files:**
- Modify: `src/hcp_cms/ui/main_window.py`

- [ ] **Step 1: 移除 _apply_dark_theme 方法**

刪除 `main_window.py` 中的 `_apply_dark_theme` 方法（已被 `_apply_theme` 取代）。確認 `__init__` 中沒有對它的引用（應只剩 `else: self._apply_dark_theme()` 的回退分支，也一併移除，因為 `theme_mgr` 一定會被提供）。

- [ ] **Step 2: 移除所有 View 中 _setup_ui 殘留的硬編碼色碼**

全面搜尋所有 UI 檔案中是否還有未遷移的 `#111827`、`#1e293b`、`#f1f5f9`、`#e2e8f0`、`#94a3b8`、`#64748b`、`#334155` 等色碼。將它們替換為 palette 引用。

例外（不需替換）：
- KPI 邊框色 `#3b82f6`、`#10b981`、`#f59e0b`、`#8b5cf6`（語義固定色）
- Mantis 狀態色 `_status_colors`（語義固定色）
- 連線狀態色 `#34d399`、`#166534`（語義固定色）

- [ ] **Step 3: 完整測試 + Lint**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v --timeout=10
.venv/Scripts/ruff.exe check src/ tests/
.venv/Scripts/ruff.exe format src/ tests/
```
預期：全部 PASSED，無 lint 錯誤

- [ ] **Step 4: 手動驗證所有頁面**

```bash
.venv/Scripts/python.exe -m hcp_cms
```

逐一切換到所有 8 個頁面，在深色/淺色模式下驗證：
1. 儀表板 — KPI 卡片、表格
2. 案件管理 — 列表、詳情對話框
3. KMS 知識庫 — 搜尋、智慧查詢
4. 信件處理 — 連線按鈕、tab、HTML 預覽
5. Mantis 同步 — 狀態標籤
6. 報表中心 — 標題、狀態
7. 規則設定 — 說明卡片、表格
8. 系統設定 — 外觀區塊、移機提醒
9. F1 說明對話框

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 移除舊 _apply_dark_theme，清理殘留硬編碼色碼"
```
