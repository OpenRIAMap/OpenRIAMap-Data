from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SessionState:
    session_id: str
    session_started_at: datetime
    session_sequence_id: int = 1
    mode: Optional[str] = None
    staging_mode: str = "empty"  # empty / manual / package
    pending_split: List[Dict[str, Any]] = field(default_factory=list)
    pending_pictures: List[Dict[str, Any]] = field(default_factory=list)
    pending_delete: List[Dict[str, Any]] = field(default_factory=list)
    pending_merge: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blocking: List[str] = field(default_factory=list)
    loaded_sources: List[str] = field(default_factory=list)
    load_history: List[Dict[str, Any]] = field(default_factory=list)
    last_precheck_report_path: Optional[str] = None
    last_commit_report_path: Optional[str] = None
    last_push_report_path: Optional[str] = None
    last_commit_summary: Dict[str, Any] = field(default_factory=dict)
    last_commit_change_stats: Dict[str, Any] = field(default_factory=dict)
    last_push_summary: Dict[str, Any] = field(default_factory=dict)
    current_session_log_path: Optional[str] = None
    current_commit_log_paths: List[str] = field(default_factory=list)
    current_push_log_paths: List[str] = field(default_factory=list)
    current_temp_paths: List[str] = field(default_factory=list)
    session_dir: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=lambda: {
        "json_total_objects": 0,
        "json_recognized_objects": 0,
        "json_skipped_objects": 0,
        "json_duplicate_ids": 0,
    })
    conflict_details: Dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.mode = None
        self.staging_mode = "empty"
        self.pending_split.clear()
        self.pending_pictures.clear()
        self.pending_delete.clear()
        self.pending_merge.clear()
        self.warnings.clear()
        self.blocking.clear()
        self.loaded_sources.clear()
        self.load_history.clear()
        self.stats = {
            "json_total_objects": 0,
            "json_recognized_objects": 0,
            "json_skipped_objects": 0,
            "json_duplicate_ids": 0,
        }
        self.conflict_details.clear()

    def clear_command_context(self) -> None:
        self.mode = None

    def has_pending_changes(self) -> bool:
        return any([
            self.pending_split,
            self.pending_pictures,
            self.pending_delete,
            self.pending_merge,
        ])

    def has_blocking(self) -> bool:
        return bool(self.blocking)

    def enter_manual_mode_if_needed(self) -> bool:
        if self.staging_mode == "empty":
            self.staging_mode = "manual"
            return True
        if self.staging_mode == "manual":
            return True
        return False

    def enter_package_mode(self) -> bool:
        if self.staging_mode == "empty":
            self.staging_mode = "package"
            return True
        return False

    def register_loaded_source(self, source_type: str, source_name: str, meta: Optional[Dict[str, Any]] = None) -> None:
        value = f"{source_type}:{source_name}"
        self.loaded_sources.append(value)
        self.load_history.append({
            "type": source_type,
            "name": source_name,
            "meta": meta or {},
        })

    def register_commit_log(self, path: str) -> None:
        self.current_commit_log_paths.append(path)

    def register_push_log(self, path: str) -> None:
        self.current_push_log_paths.append(path)

    def register_temp_path(self, path: str) -> None:
        self.current_temp_paths.append(path)
