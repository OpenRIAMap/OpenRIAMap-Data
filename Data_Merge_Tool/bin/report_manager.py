from __future__ import annotations

from pathlib import Path
from datetime import datetime


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


class ReportManager:
    def __init__(self, reports_root: Path) -> None:
        self.reports_root = reports_root
        self.latest_root = reports_root / "latest"
        self.archive_root = reports_root / "archive"
        ensure_dir(self.latest_root)
        ensure_dir(self.archive_root)

    def _write_pair(self, latest_name: str, archive_suffix: str, text: str) -> tuple[Path, Path]:
        latest = self.latest_root / latest_name
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = self.archive_root / f"{ts}_{archive_suffix}"
        latest.write_text(text, encoding="utf-8")
        archive.write_text(text, encoding="utf-8")
        return latest, archive

    def write_precheck_report(self, text: str) -> tuple[Path, Path]:
        return self._write_pair("precheck_report.md", "precheck.md", text)

    def write_commit_report(self, text: str) -> tuple[Path, Path]:
        return self._write_pair("commit_report.md", "commit.md", text)

    def write_push_report(self, text: str) -> tuple[Path, Path]:
        return self._write_pair("push_report.md", "push.md", text)

    def write_env_check_report(self, text: str) -> tuple[Path, Path]:
        return self._write_pair("env_check_report.md", "env_check.md", text)
