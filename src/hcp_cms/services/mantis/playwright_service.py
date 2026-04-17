"""PlaywrightMantisService — 瀏覽器自動化讀取 Mantis Issue 狀態。"""

from __future__ import annotations

import threading
from collections.abc import Callable

_LOGIN_TIMEOUT_SEC = 300  # 5 分鐘


class PlaywrightMantisService:
    """以 Playwright Chromium 開啟 Mantis，等待使用者登入後擷取 Issue 資料。

    使用方式：
        svc = PlaywrightMantisService(mantis_url="https://mantis.example.com")
        svc.open_browser()
        # ... 等待使用者按「已登入」按鈕 ...
        svc.confirm_login()
        data = svc.fetch_issue("0015659")
    """

    def __init__(self, mantis_url: str) -> None:
        self._mantis_url = mantis_url.rstrip("/")
        self._page = None
        self._browser = None
        self._playwright = None
        self._login_event = threading.Event()

    def open_browser(self) -> None:
        """啟動 Chromium 並導向 Mantis 登入頁。"""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._page = self._browser.new_page()
        self._page.goto(f"{self._mantis_url}/login_page.php")

    def confirm_login(self) -> None:
        """使用者按下「已登入」後呼叫，解除等待封鎖。"""
        self._login_event.set()

    def fetch_issue(self, issue_no: str) -> dict | None:
        """擷取單一 Issue 的狀態資料（需在 confirm_login() 之後呼叫）。"""
        if self._page is None:
            return None
        try:
            url = f"{self._mantis_url}/view.php?id={issue_no}"
            self._page.goto(url)
            self._page.wait_for_load_state("networkidle", timeout=10000)
            return self._extract_issue_data(issue_no)
        except Exception:
            return None

    def _extract_issue_data(self, issue_no: str) -> dict:
        """從 Mantis Issue 頁面擷取追蹤欄位。

        ⚠️ DOM 選擇器需在實際 Mantis 環境執行 POC 後調整。
        以下為預設佔位，POC 時以瀏覽器 DevTools 確認正確選擇器。
        """
        data: dict = {"issue_no": issue_no}
        try:
            notes = self._page.query_selector_all(".bugnote-note")  # type: ignore[union-attr]
            data["notes"] = [n.inner_text() for n in notes]
            status_el = self._page.query_selector("[data-column='status'] .column-value")  # type: ignore[union-attr]
            data["status"] = status_el.inner_text() if status_el else None
        except Exception:
            pass
        return data

    def fetch_issues_batch(self, issue_nos: list[str],
                           on_progress: Callable[[str, dict | None], None] | None = None) -> list[dict]:
        """批次擷取多個 Issue，每筆完成後呼叫 on_progress 回調。"""
        results = []
        for no in issue_nos:
            data = self.fetch_issue(no)
            results.append(data or {"issue_no": no})
            if on_progress:
                on_progress(no, data)
        return results

    def close(self) -> None:
        """關閉瀏覽器並釋放資源。"""
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._page = None
            self._browser = None
            self._playwright = None
