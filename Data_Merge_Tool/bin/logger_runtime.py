from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json


def _json_safe(obj):
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(x) for x in obj]
    return obj


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


class RuntimeLogManager:
    def __init__(self, logs_root: Path, session_id: str) -> None:
        self.logs_root = logs_root
        self.session_commit_root = logs_root / "session_commit"
        self.push_root = logs_root / "push"
        ensure_dir(self.session_commit_root)
        ensure_dir(self.push_root)
        self.session_id = session_id
        self.session_log_path: Path | None = None

    def _ts(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def open_session_log(self, tool_version: str, repo_root: str) -> Path:
        self.session_log_path = self.session_commit_root / f"session_{self._ts()}.log"
        header = [
            "==== OpenRIAMap Data Tool Session Log ====",
            f"Session-Id: {self.session_id}",
            f"Started-At: {datetime.now().isoformat(timespec='seconds')}",
            f"Tool-Version: {tool_version}",
            f"Repo-Root: {repo_root}",
            "==========================================",
            "",
        ]
        self.session_log_path.write_text("\n".join(header), encoding="utf-8")
        return self.session_log_path

    def write_session_event(self, raw_command: str, normalized_command: str, args: str, success: bool, summary: str, duration_ms: int = 0) -> None:
        if not self.session_log_path:
            return
        lines = [
            f"[{datetime.now().isoformat(timespec='seconds')}]",
            f"raw={raw_command}",
            f"command={normalized_command}",
            f"args={args}",
            f"success={success}",
            f"duration_ms={duration_ms}",
            f"summary={summary}",
            "",
        ]
        with self.session_log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def write_commit_log(self, summary: dict) -> Path:
        path = self.session_commit_root / f"commit_{self._ts()}.log"
        lines = [
            "==== OpenRIAMap Data Tool Commit Log ====",
            f"Session-Id: {self.session_id}",
            f"Created-At: {datetime.now().isoformat(timespec='seconds')}",
            json.dumps(_json_safe(summary), ensure_ascii=False, indent=2),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def write_push_log(self, summary: dict) -> Path:
        path = self.push_root / f"push_{self._ts()}.log"
        lines = [
            "==== OpenRIAMap Data Tool Push Log ====",
            f"Session-Id: {self.session_id}",
            f"Created-At: {datetime.now().isoformat(timespec='seconds')}",
            json.dumps(_json_safe(summary), ensure_ascii=False, indent=2),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


def build_frozen_push_log_text(self, summary: dict) -> str:
    summary = _json_safe(summary)
    lines = [
        "==== OpenRIAMap Data Push Log ====",
        f"Session-Id: {self.session_id}",
        f"Created-At: {datetime.now().isoformat(timespec='seconds')}",
    ]
    for key, value in summary.items():
        if isinstance(value, (dict, list)):
            lines.append(f"{key}: {json.dumps(_json_safe(value), ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {value}")
    lines += [
        "",
        "[Intent]",
        "This log is generated before git commit/pull/push and is intended to be committed together with this push operation.",
        "If the push workflow fails before a valid data push is formed, this log should be removed locally.",
        "",
        "Final-State: INTENDED_FOR_THIS_PUSH",
        "=================================",
        "",
    ]
    return "\n".join(lines)

def create_pending_push_log(self, summary: dict) -> Path:
    path = self.push_root / f"push_{self._ts()}.log"
    path.write_text(self.build_frozen_push_log_text(summary), encoding="utf-8")
    return path
