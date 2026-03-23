"""Report generation background job."""

from __future__ import annotations

import calendar
import sqlite3
from datetime import datetime
from pathlib import Path

from hcp_cms.core.report_engine import ReportEngine


class ReportJob:
    """Generates scheduled reports."""

    def __init__(self, conn: sqlite3.Connection, output_dir: Path) -> None:
        self._engine = ReportEngine(conn)
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, year: int | None = None, month: int | None = None) -> dict[str, Path]:
        """Generate tracking table and monthly report. Returns dict of paths."""
        now = datetime.now()
        y = year or now.year
        m = month or now.month

        last_day = calendar.monthrange(y, m)[1]
        start_date = f"{y}/{m:02d}/01"
        end_date = f"{y}/{m:02d}/{last_day:02d}"

        tracking_path = self._output_dir / f"CS_追蹤表_{y}{m:02d}.xlsx"
        report_path = self._output_dir / f"CS_月報_{y}{m:02d}.xlsx"

        self._engine.generate_tracking_table(start_date, end_date, tracking_path)
        self._engine.generate_monthly_report(start_date, end_date, report_path)

        return {"tracking": tracking_path, "report": report_path}
