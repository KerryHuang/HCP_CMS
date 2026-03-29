# 主題系統設計規格（深色/淺色模式）

## 概述

為 HCP CMS 建立深色/淺色雙主題系統，支援即時切換、跟隨 Windows 系統設定、使用者手動覆蓋。

## 需求摘要

| 項目 | 決策 |
|------|------|
| 觸發方式 | 預設跟隨系統，可手動覆蓋 |
| 切換體驗 | 即時切換，不需重啟 |
| 淺色配色 | Tailwind Slate 系列（與深色同色系，明暗反轉） |
| 偏好儲存 | 獨立 `config.json` 檔案（與 DB 同目錄） |
| HTML 內容 | 信件預覽、說明對話框皆跟隨主題切換 |

## 架構

### 1. ColorPalette — 語義色彩定義

新增 `src/hcp_cms/ui/theme.py`，以 `@dataclass(frozen=True)` 定義 `ColorPalette`：

```python
@dataclass(frozen=True)
class ColorPalette:
    # 背景
    bg_primary: str      # 主視窗背景
    bg_secondary: str    # 卡片、輸入框、表格背景
    bg_sidebar: str      # 側邊欄
    bg_code: str         # 程式碼/唯讀區
    bg_hover: str        # Hover 狀態

    # 文字
    text_primary: str    # 主要文字（標題）
    text_secondary: str  # 一般文字
    text_tertiary: str   # 標籤、提示
    text_muted: str      # 次要標籤
    text_faint: str      # 極淡提示

    # 強調色
    accent: str          # 連結、選中項目
    accent_button: str   # 按鈕背景
    accent_button_hover: str  # 按鈕 hover

    # 邊框
    border_primary: str  # 輸入框邊框
    border_secondary: str # 分隔線

    # 狀態色
    success: str         # 綠色
    error: str           # 紅色
    warning: str         # 黃色
```

#### 深色主題色碼（現有）

| 語義 | 色碼 | Tailwind |
|------|------|----------|
| `bg_primary` | `#111827` | slate-950 |
| `bg_secondary` | `#1e293b` | slate-800 |
| `bg_sidebar` | `#0f172a` | slate-950 |
| `bg_code` | `#0f172a` | slate-950 |
| `bg_hover` | `#273344` | — |
| `text_primary` | `#f1f5f9` | slate-100 |
| `text_secondary` | `#e2e8f0` | slate-200 |
| `text_tertiary` | `#94a3b8` | slate-400 |
| `text_muted` | `#64748b` | slate-500 |
| `text_faint` | `#475569` | slate-600 |
| `accent` | `#60a5fa` | sky-400 |
| `accent_button` | `#1e40af` | blue-800 |
| `accent_button_hover` | `#2563eb` | blue-600 |
| `border_primary` | `#334155` | slate-700 |
| `border_secondary` | `#1e293b` | slate-800 |
| `success` | `#4ade80` | green-400 |
| `error` | `#ef4444` | red-500 |
| `warning` | `#fbbf24` | amber-400 |

#### 淺色主題色碼（新增）

| 語義 | 色碼 | Tailwind |
|------|------|----------|
| `bg_primary` | `#f8fafc` | slate-50 |
| `bg_secondary` | `#ffffff` | white |
| `bg_sidebar` | `#f1f5f9` | slate-100 |
| `bg_code` | `#f1f5f9` | slate-100 |
| `bg_hover` | `#e2e8f0` | slate-200 |
| `text_primary` | `#0f172a` | slate-900 |
| `text_secondary` | `#1e293b` | slate-800 |
| `text_tertiary` | `#475569` | slate-600 |
| `text_muted` | `#64748b` | slate-500 |
| `text_faint` | `#94a3b8` | slate-400 |
| `accent` | `#2563eb` | blue-600 |
| `accent_button` | `#2563eb` | blue-600 |
| `accent_button_hover` | `#1d4ed8` | blue-700 |
| `border_primary` | `#cbd5e1` | slate-300 |
| `border_secondary` | `#e2e8f0` | slate-200 |
| `success` | `#16a34a` | green-600 |
| `error` | `#dc2626` | red-600 |
| `warning` | `#d97706` | amber-600 |

### 2. ThemeManager — 主題管理器

```python
class ThemeManager(QObject):
    theme_changed = Signal(ColorPalette)

    def __init__(self, config_dir: Path):
        self._current: str = "system"  # "dark" | "light" | "system"
        self._palette: ColorPalette = DARK_PALETTE
        self._config_path = config_dir / "config.json"

    def set_theme(self, mode: str) -> None:
        """切換主題，更新 palette，發出 theme_changed Signal，儲存 config"""

    def current_palette(self) -> ColorPalette:
        """取得當前色彩組"""

    def current_mode(self) -> str:
        """取得當前模式字串"""

    def _resolve_system_theme(self) -> str:
        """讀取 Windows Registry AppsUseLightTheme，回傳 'dark' 或 'light'"""

    def _load_config(self) -> None:
        """從 config.json 載入偏好。檔案不存在或格式錯誤時使用預設值"""

    def _save_config(self) -> None:
        """儲存偏好到 config.json"""
```

**設計決策：**

- `ThemeManager` 歸屬 UI 層（`src/hcp_cms/ui/theme.py`），不涉及業務邏輯
- `config.json` 讀寫由 `ThemeManager` 自行處理，不經過 Data 層
- 單例模式：`app.py` 建立唯一實例，向下傳遞

### 3. config.json 格式

```json
{
  "theme": "system"
}
```

- 位置：`db_dir/config.json`（與 SQLite DB 同目錄）
- `theme` 值：`"system"` | `"dark"` | `"light"`
- 檔案不存在時自動建立，預設 `"system"`

### 4. 啟動流程

```
app.main()
  └─ DatabaseManager(db_path).initialize()
  └─ ThemeManager(db_dir)
       ├─ _load_config()  → 讀取 config.json
       ├─ _resolve_system_theme()  → 若 "system" 則偵測 Windows
       └─ _palette = DARK_PALETTE 或 LIGHT_PALETTE
  └─ MainWindow(conn, db_dir, theme_mgr)
       ├─ _apply_theme(theme_mgr.current_palette())  → 套用全域樣式
       └─ 各 View(conn, theme_mgr)
            └─ theme_mgr.theme_changed.connect(self._apply_theme)
```

### 5. 各 View 改造模式

每個 View / Dialog 做三件事：

1. **接收 `ThemeManager`** — 建構子增加 `theme_mgr: ThemeManager` 參數
2. **連接 Signal** — `theme_mgr.theme_changed.connect(self._apply_theme)`
3. **抽出 `_apply_theme(palette: ColorPalette)`** — 將 `setStyleSheet()` 的色碼改為引用 `palette` 屬性

```python
# 改造前
title.setStyleSheet("color: #64748b; font-size: 11px;")

# 改造後
def _apply_theme(self, p: ColorPalette) -> None:
    self._title.setStyleSheet(f"color: {p.text_muted}; font-size: 11px;")
```

**影響範圍：**

| 檔案 | setStyleSheet 數量 | 改動程度 |
|------|-------------------|---------|
| `main_window.py` | ~150 行全域 QSS | 高 |
| `dashboard_view.py` | 8 處 | 中 |
| `case_detail_dialog.py` | 11 處 | 中 |
| `email_view.py` | 8 處 + HTML CSS | 高 |
| `help_dialog.py` | 嵌入式 CSS | 中 |
| `kms_view.py` | 8 處 | 中 |
| `rules_view.py` | 6 處 | 中 |
| `mantis_view.py` | 8 處 | 中 |
| 其餘 6 個 View/Dialog | 2-4 處 | 低 |

### 6. HTML 內容主題切換

`email_view.py` 的 `_BASE_STYLE` 和 `help_dialog.py` 的 `_DARK_CSS` 改為根據當前 palette 動態生成 CSS 字串的方法。切換主題時重新載入頁面內容。

### 7. 設定頁面 UI

在 `settings_view.py` 現有設定項目上方新增「外觀」區段：

```
┌─ 外觀 ──────────────────────────┐
│  主題模式：  ○ 跟隨系統  ○ 深色  ○ 淺色  │
└──────────────────────────────────┘
```

- 使用 `QRadioButton` 三選一
- 選擇後立即生效（即時切換），同時寫入 `config.json`
- 預設值：「跟隨系統」

### 8. 系統主題即時跟隨

不主動監聽 Windows Registry 變化。當設定為「跟隨系統」時，在 `MainWindow.changeEvent()` 偵測 `ActivationChange` 事件，重新檢查系統設定並在必要時切換主題。

### 9. 動態狀態色

Mantis 狀態色、KPI 邊框色等語義色不隨主題變化，兩套主題共用同一組值或僅微調明暗度。在 `ColorPalette` 的 `success` / `error` / `warning` 欄位中定義。

## 測試策略

**單元測試（`tests/unit/test_theme.py`）：**

| 測試項目 | 說明 |
|---------|------|
| `TestColorPalette` | 驗證深色/淺色兩組 palette 所有欄位都有值、格式為 `#xxxxxx` |
| `TestThemeManager.test_default_theme` | 無 config.json 時預設為 `"system"` |
| `TestThemeManager.test_set_dark` | 切換為深色，`current_palette()` 返回 `DARK_PALETTE` |
| `TestThemeManager.test_set_light` | 切換為淺色，`current_palette()` 返回 `LIGHT_PALETTE` |
| `TestThemeManager.test_signal_emitted` | 切換時 `theme_changed` Signal 有發出 |
| `TestThemeManager.test_save_load_config` | 儲存後重新載入，偏好值一致 |
| `TestThemeManager.test_invalid_config` | config.json 格式錯誤時回退為預設值 |

**不測試：** Windows Registry 偵測（平台相依）、各 View 視覺呈現（QSS 渲染，人眼驗證）。
