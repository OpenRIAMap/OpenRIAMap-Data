from __future__ import annotations

import cmd
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from archive_builder import build_zip, copy_tree_contents, prepare_archive_workspace, write_manifest
from command_registry import ALIAS_TO_COMMAND, COMMAND_ALIASES, VALID_COMMANDS
from env_check import run_env_checks
from git_utils import (
    GitCommandError,
    get_current_branch,
    get_git_head_hash,
    get_remote_url,
    git_add_all,
    git_commit,
    git_pull_rebase,
    git_push,
    git_status_porcelain,
)
from github_release_api import (
    GitHubReleaseError,
    ensure_monthly_release,
    find_release_asset,
    list_release_assets,
    upload_release_asset,
)
from logger_runtime import RuntimeLogManager
from report_manager import ReportManager
from session_state import SessionState

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
TOOL_CONFIG_PATH = CONFIG_DIR / "tool_config.json"
POLICY_CONFIG_PATH = CONFIG_DIR / "policy_config.json"
TZ_8 = timezone(timedelta(hours=8))
INVALID_WINDOWS_CHARS = set('\\/:*?"<>|')
TOOL_VERSION = "v5.0"

DEFAULT_RUNTIME = {
    "github": {
        "cold_repo": "OpenRIAMap/ColdToolArchive",
        "cold_token_env": "OPENRIAMAP_COLD_PAT",
        "data_remote_name": "origin",
        "data_branch": "main",
    },
    "push": {
        "clean_source_data_after_push": True,
        "clean_workspace_after_push": True,
        "verify_release_asset": True,
    },
}


def now_iso() -> str:
    return datetime.now(TZ_8).isoformat(timespec="seconds")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_field(obj: dict, *keys):
    for k in keys:
        if k in obj:
            return obj[k]
    return None


def normalize_text(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s != "" else None


def is_safe_filename_component(value: str):
    if value is None:
        return False, "为空"
    if any(ch in INVALID_WINDOWS_CHARS for ch in value):
        bad = "".join(sorted({ch for ch in value if ch in INVALID_WINDOWS_CHARS}))
        return False, f"包含 Windows 文件名非法字符: {bad}"
    if value.endswith(" ") or value.endswith("."):
        return False, "不能以空格或点结尾"
    upper = value.upper()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if upper in reserved:
        return False, f"为 Windows 保留名: {value}"
    return True, ""


def merge_config(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_config(out[k], v)
        else:
            out[k] = v
    return out


class ToolShell(cmd.Cmd):
    intro = "OpenRIAMap 数据维护工具 v5\n输入 help 或 hp 查看命令说明。"
    prompt = "> "

    def __init__(self) -> None:
        super().__init__()
        self.tool_config = merge_config(DEFAULT_RUNTIME, read_json(TOOL_CONFIG_PATH))
        self.policy = read_json(POLICY_CONFIG_PATH)
        self.root = ROOT
        self.source_data = self.root / self.tool_config["paths"]["source_data"]
        self.workspace = self.root / self.tool_config["paths"]["workspace"]
        self.logs = self.root / self.tool_config["paths"]["logs"]
        self.reports_root = self.root / "reports"
        self.web_schema_root = self.root / self.tool_config["paths"]["web_schema"]
        self.web_schema_source = self.web_schema_root / "source"
        self.web_schema_cache = self.web_schema_root / "cache"
        ensure_dir(self.source_data)
        ensure_dir(self.workspace)
        ensure_dir(self.logs)
        ensure_dir(self.reports_root)
        ensure_dir(self.web_schema_source)
        ensure_dir(self.web_schema_cache)
        self.repo_root = (self.root / self.tool_config["repository_root"]).resolve()
        self.world_map_path = self.web_schema_cache / "world_map.json"
        self.special_class_rules_path = self.web_schema_cache / "special_class_rules.json"
        self.feature_classes_path = self.web_schema_cache / "feature_classes.json"
        self.workflow_kind_registry_path = self.web_schema_cache / "workflow_kind_registry.json"
        self.world_map = self._load_world_map()
        self.special_class_set = self._load_special_classes()
        self.feature_class_set = self._load_feature_classes()
        self.workflow_kind_registry = self._load_workflow_kind_registry()
        session_id = f"S{datetime.now().strftime('%Y%m%d-%H%M%S')}-001"
        self.state = SessionState(session_id=session_id, session_started_at=datetime.now(TZ_8))
        self.log_manager = RuntimeLogManager(self.logs, session_id)
        self.report_manager = ReportManager(self.reports_root)
        self.state.current_session_log_path = str(self.log_manager.open_session_log(TOOL_VERSION, str(self.repo_root)))
        self._new_session_dir()
        self.command_handlers = self._build_command_registry()

    # ---------- base properties ----------
    @property
    def split_root(self):
        return self.repo_root / "Data_Spilt"

    @property
    def merge_root(self):
        return self.repo_root / "Data_Merge"

    @property
    def picture_root(self):
        return self.repo_root / "Picture"

    # ---------- command registry ----------
    def _build_command_registry(self):
        return {
            "help": self.do_help,
            "status": self.do_status,
            "load-package": self.do_load_package,
            "load-json": self.do_load_json,
            "load-image": self.do_load_image,
            "preview": self.do_preview,
            "report": self.do_report,
            "commit": self.do_commit,
            "rebuild": self.do_rebuild,
            "discard": self.do_discard,
            "clear": self.do_clear,
            "sync-web-schema": self.do_sync_web_schema,
            "push": self.do_push,
            "push-data": self.do_push_data,
            "push-cold": self.do_push_cold,
            "check-env": self.do_check_env,
            "exit": self.do_exit,
        }

    def parseline(self, line: str):
        cmd_name, arg, line = super().parseline(line)
        if cmd_name in ALIAS_TO_COMMAND:
            cmd_name = ALIAS_TO_COMMAND[cmd_name]
            line = f"{cmd_name} {arg}".strip()
        return cmd_name, arg, line

    def default(self, line):
        parts = line.strip().split(maxsplit=1)
        cmd_name = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        if cmd_name in ALIAS_TO_COMMAND:
            cmd_name = ALIAS_TO_COMMAND[cmd_name]
        if cmd_name in self.command_handlers:
            return self._dispatch_command(cmd_name, args, raw_command=line.strip())
        print(f"未知指令：{line.strip()}。输入 help / hp 查看可用命令。")

    def onecmd(self, line: str):
        if not line.strip():
            return False
        cmd_name, arg, _ = self.parseline(line)
        if cmd_name in self.command_handlers:
            return self._dispatch_command(cmd_name, arg, raw_command=line.strip())
        return super().onecmd(line)

    def _dispatch_command(self, cmd_name: str, args: str, raw_command: str):
        start = time.time()
        allowed, reason = self._check_command_allowed(cmd_name)
        if not allowed:
            print(reason)
            self.log_manager.write_session_event(raw_command, cmd_name, args, False, reason, int((time.time()-start)*1000))
            return False
        try:
            result = self.command_handlers[cmd_name](args)
            summary = "完成"
            stop = False
            if result is True:
                stop = True
                summary = "退出工具"
            elif isinstance(result, str):
                summary = result
            elif isinstance(result, dict):
                summary = result.get("summary", "完成")
                stop = bool(result.get("stop", False))
            self.log_manager.write_session_event(raw_command, cmd_name, args, True, summary, int((time.time()-start)*1000))
            return stop
        except Exception as e:
            print(f"执行失败：{e}")
            self.log_manager.write_session_event(raw_command, cmd_name, args, False, str(e), int((time.time()-start)*1000))
            return False

    def _check_command_allowed(self, cmd_name: str) -> tuple[bool, str]:
        if cmd_name in {"help", "status", "preview", "report", "clear", "discard", "sync-web-schema", "check-env", "exit"}:
            return True, "OK"
        if cmd_name in {"push", "push-cold", "push-data"}:
            if self.state.staging_mode != "empty" or self.state.has_pending_changes():
                return False, "push 执行失败：当前仍存在未提交或未清理的 staging 内容。请先执行 commit 或 discard。"
            if self.state.has_blocking():
                return False, "push 执行失败：当前存在 blocking 问题。请先处理。"
            return True, "OK"
        if cmd_name == "load-package":
            if self.state.staging_mode != "empty":
                return False, "当前 staging 为手动叠加或 package 独占模式，因此 load-package 不可用。请先 commit 或 discard。"
        if cmd_name in {"load-json", "load-image"} and self.state.staging_mode == "package":
            return False, "当前 staging 为 package 独占模式，因此 load-json / load-image 不可用。"
        if cmd_name == "commit":
            if not self.state.has_pending_changes():
                return False, "当前没有待提交内容。"
            if self.state.has_blocking():
                return False, "当前存在阻断问题，不能提交。请先执行 report 查看详情。"
        return True, "OK"

    # ---------- misc helpers ----------
    def _policy(self, section, key, default=None):
        return self.policy.get(section, {}).get(key, default)

    def _new_session_dir(self):
        session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir = self.workspace / session_name
        ensure_dir(session_dir)
        self.state.session_dir = str(session_dir)

    def _load_world_map(self):
        if self.world_map_path.exists():
            try:
                data = read_json(self.world_map_path)
                return {k: v for k, v in data.items() if not k.startswith("_")}
            except Exception:
                return {}
        return {}

    def _load_special_classes(self):
        if self.special_class_rules_path.exists():
            try:
                data = read_json(self.special_class_rules_path)
                return set(data.get("special_classes", []))
            except Exception:
                return set()
        return set()

    def _load_feature_classes(self):
        if self.feature_classes_path.exists():
            try:
                return set(read_json(self.feature_classes_path).get("feature_classes", []))
            except Exception:
                return set()
        return set()

    def _load_workflow_kind_registry(self):
        if self.workflow_kind_registry_path.exists():
            try:
                return read_json(self.workflow_kind_registry_path).get("workflow_kinds", {})
            except Exception:
                return {}
        return {}

    def _append_unique(self, target_list, value, key=None):
        if key is None:
            if value not in target_list:
                target_list.append(value)
                return True
            return False
        seen = {key(x) for x in target_list}
        kv = key(value)
        if kv not in seen:
            target_list.append(value)
            return True
        return False

    def _apply_severity(self, severity, message):
        if severity == "blocking":
            self.state.blocking.append(message)
        else:
            self.state.warnings.append(message)

    def _is_special_class(self, class_name):
        return class_name in self.special_class_set

    def _validate_schema_fields(self, class_name: str, kind: str | None):
        if self.feature_class_set and class_name not in self.feature_class_set:
            self._apply_severity(self._policy("schema_policy", "unknown_class", "blocking"), f"未知 Class：{class_name}")
        if class_name in self.workflow_kind_registry and kind:
            valid = {str(x) for x in self.workflow_kind_registry.get(class_name, [])}
            if valid and kind not in valid:
                self._apply_severity(self._policy("schema_policy", "unknown_kind", "blocking"), f"未知 Kind：{class_name}/{kind}")

    def resolve_world_dir_name(self, world):
        if isinstance(world, int):
            key = str(world)
            if self._policy("world_policy", "allow_numeric_world_code", True) and key in self.world_map:
                return self.world_map[key]
        if isinstance(world, str) and world.isdigit():
            if self._policy("world_policy", "allow_numeric_world_code", True) and world in self.world_map:
                return self.world_map[world]
        if isinstance(world, str) and self._policy("world_policy", "allow_string_world_id", True) and world.strip():
            return world.strip()
        sev = self._policy("world_policy", "unknown_world", "blocking")
        self._apply_severity(sev, f"未知 World，无法解析目录名：{world}")
        return str(world)

    def _split_leaf_dir(self, world, class_name, kind):
        p = self.split_root / self.resolve_world_dir_name(world) / class_name
        if self._is_special_class(class_name):
            if not kind:
                raise ValueError(f"特殊类 {class_name} 缺少 kind")
            p = p / kind
        return p

    def _merge_leaf_dir(self, world, class_name, kind):
        p = self.merge_root / self.resolve_world_dir_name(world) / class_name
        if self._is_special_class(class_name):
            if not kind:
                raise ValueError(f"特殊类 {class_name} 缺少 kind")
            p = p / kind
        return p

    def _picture_leaf_dir(self, world, class_name, kind):
        p = self.picture_root / self.resolve_world_dir_name(world) / class_name
        if self._is_special_class(class_name):
            if not kind:
                raise ValueError(f"特殊类 {class_name} 缺少 kind")
            p = p / kind
        return p

    def _new_item_brief(self, obj: dict) -> dict:
        item_id = normalize_text(get_field(obj, "ID", "id"))
        class_name = normalize_text(get_field(obj, "Class", "class"))
        world = get_field(obj, "World", "world")
        kind = normalize_text(get_field(obj, "Kind", "kind"))
        return {"id": item_id, "class": class_name, "world": world, "kind": kind, "obj": obj}

    def _build_precheck_report(self, title):
        lines = [
            "# 预校验报告", "",
            f"时间：{now_iso()}",
            f"说明：{title}", "",
            "## 摘要",
            f"- staging_mode：{self.state.staging_mode}",
            f"- mode：{self.state.mode or '-'}",
            f"- loaded_sources：{len(self.state.loaded_sources)}",
            f"- 待写入 Split：{len(self.state.pending_split)}",
            f"- 待写入图片：{len(self.state.pending_pictures)}",
            f"- 待删除：{len(self.state.pending_delete)}",
            f"- 待重建 Merge：{len(self.state.pending_merge)}",
            f"- 警告：{len(self.state.warnings)}",
            f"- 阻断：{len(self.state.blocking)}",
            "",
            "## 已载入来源",
        ]
        lines += [f"- {x}" for x in self.state.loaded_sources] if self.state.loaded_sources else ["- 无"]
        if self.state.mode == "json":
            lines += ["", "## JSON 识别统计",
                      f"- 读取对象总数：{self.state.stats['json_total_objects']}",
                      f"- 成功识别候选要素：{self.state.stats['json_recognized_objects']}",
                      f"- 跳过对象数：{self.state.stats['json_skipped_objects']}",
                      f"- 同批重复 ID 数：{self.state.stats['json_duplicate_ids']}"]
        lines += ["", "## 阻断问题"]
        lines += [f"- {x}" for x in self.state.blocking] if self.state.blocking else ["- 无"]
        lines += ["", "## 警告"]
        lines += [f"- {x}" for x in self.state.warnings] if self.state.warnings else ["- 无"]
        return "\n".join(lines)

    def _write_precheck(self, title: str) -> Path:
        latest, archive = self.report_manager.write_precheck_report(self._build_precheck_report(title))
        self.state.last_precheck_report_path = str(latest)
        return latest

    # ---------- scanning ----------
    def _scan_json_inputs(self):
        base = self.source_data / "json_inputs"
        files = sorted(base.rglob("*.json")) if self._policy("scan_policy", "recursive_json_scan", True) else sorted(base.glob("*.json"))
        return [{"path": p, "relative": str(p.relative_to(base)), "size": p.stat().st_size} for p in files]

    def _scan_image_inputs(self):
        base = self.source_data / "image_inputs"
        exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        files = sorted([p for p in (base.rglob("*") if self._policy("scan_policy", "recursive_image_scan", True) else base.glob("*")) if p.is_file() and p.suffix.lower() in exts])
        return [{"path": p, "relative": str(p.relative_to(base)), "size": p.stat().st_size} for p in files]

    def _scan_relay_packages(self):
        base = self.source_data / "relay_packages"
        ensure_dir(base)
        files = sorted(base.rglob("*")) if self._policy("scan_policy", "recursive_package_scan", True) else sorted(base.glob("*"))
        results = []
        for p in files:
            if p.is_dir() or p.suffix.lower() == ".zip":
                results.append({"path": p, "relative": str(p.relative_to(base)), "size": p.stat().st_size if p.is_file() else 0})
        return results

    def _extract_package_zip(self, zip_path: Path) -> Path:
        target = self.workspace / "tmp_packages" / f"{zip_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ensure_dir(target)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target)
        entries = [x for x in target.iterdir() if x.is_dir()]
        if len(entries) == 1 and (entries[0] / 'Data_Spilt').exists():
            return entries[0]
        if (target / 'Data_Spilt').exists():
            return target
        raise RuntimeError(f"zip 标准包解压后未发现有效包结构：{zip_path.name}")

    # ---------- load json/image/package ----------
    def _load_json_file(self, path: Path):
        data = read_json(path)
        items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
        recognized = []
        seen_in_file = set()
        for obj in items:
            self.state.stats["json_total_objects"] += 1
            if not isinstance(obj, dict):
                self.state.stats["json_skipped_objects"] += 1
                continue
            brief = self._new_item_brief(obj)
            item_id = brief["id"]
            class_name = brief["class"]
            world = brief["world"]
            kind = brief["kind"]
            if not item_id:
                self._apply_severity(self._policy("id_policy", "invalid_id", "blocking"), f"JSON 对象缺少 ID：{path.name}")
                continue
            ok, msg = is_safe_filename_component(item_id)
            if not ok:
                self._apply_severity(self._policy("id_policy", "invalid_id", "blocking"), f"非法 ID {item_id}: {msg}")
                continue
            if not class_name:
                self._apply_severity(self._policy("schema_policy", "unknown_class", "blocking"), f"JSON 对象缺少 Class：{item_id}")
                continue
            if world is None or world == "":
                self._apply_severity(self._policy("conflict_policy", "missing_world", "blocking"), f"JSON 对象缺少 World：{item_id}")
                continue
            if self._is_special_class(class_name) and not kind:
                self._apply_severity(self._policy("conflict_policy", "missing_kind_for_special_class", "blocking"), f"特殊类缺少 Kind：{item_id} / {class_name}")
                continue
            self._validate_schema_fields(class_name, kind)
            if item_id in seen_in_file:
                self.state.stats["json_duplicate_ids"] += 1
                self._apply_severity(self._policy("conflict_policy", "duplicate_same_structure", "warning"), f"同一 JSON 文件内重复 ID：{item_id} ({path.name})")
            seen_in_file.add(item_id)
            if any(x.get("id") == item_id for x in self.state.pending_delete):
                self.state.blocking.append(f"当前会话已将 ID 标记为删除，不能再载入 JSON：{item_id}")
            if any(x.get("id") == item_id for x in self.state.pending_split):
                self._apply_severity(self._policy("conflict_policy", "duplicate_cross_structure", "warning"), f"当前 staging 中已存在同 ID JSON：{item_id}")
            recognized.append({
                "id": item_id,
                "class": class_name,
                "world": world,
                "kind": kind,
                "obj": obj,
                "source": str(path),
            })
            self.state.stats["json_recognized_objects"] += 1
        return recognized

    def _collect_existing_ids(self):
        ids = set()
        for leaf in self.split_root.rglob("*.json"):
            if leaf.name == "INDEX.json":
                continue
            ids.add(leaf.stem)
        return ids

    def _auto_bind_image_to_existing(self, path: Path):
        stem = path.stem
        m = re.match(r"(.+?)_(\d+)$", stem)
        candidate = m.group(1) if m else stem
        existing_ids = self._collect_existing_ids()
        return candidate if candidate in existing_ids else None

    def _register_picture_append(self, item_id: str, world: str, class_name: str, kind: str | None, file_path: Path):
        target = None
        for entry in self.state.pending_pictures:
            if entry.get("id") == item_id and entry.get("group_mode") == "append":
                target = entry
                break
        if target is None:
            target = {
                "id": item_id,
                "world": world,
                "class": class_name,
                "kind": kind,
                "group_mode": "append",
                "files": [],
            }
            self.state.pending_pictures.append(target)
        if any(Path(x).name == file_path.name for x in target["files"]):
            self.state.warnings.append(f"同名图片重复导入：{file_path.name} -> {item_id}")
        target["files"].append(str(file_path))

    def _lookup_feature_metadata(self, item_id: str):
        for p in self.split_root.rglob(f"{item_id}.json"):
            if p.name == "INDEX.json":
                continue
            parts = p.relative_to(self.split_root).parts
            if len(parts) >= 3:
                world, class_name = parts[0], parts[1]
                kind = parts[2] if self._is_special_class(class_name) and len(parts) >= 4 else None
                return {"world": world, "class": class_name, "kind": kind}
        for x in self.state.pending_split:
            if x.get("id") == item_id:
                return {"world": self.resolve_world_dir_name(x.get("world")), "class": x.get("class"), "kind": x.get("kind")}
        return None

    def do_load_json(self, arg):
        self.state.mode = "json"
        if not self.state.enter_manual_mode_if_needed():
            raise RuntimeError("当前 staging 为 package 独占模式，因此 load-json 不可用。")
        entries = self._scan_json_inputs()
        if not entries:
            print("未在 source_data/json_inputs 中找到 JSON 文件。")
            return {"summary": "未发现 JSON 输入"}
        choice = arg.strip() or "all"
        selected = entries if choice == "all" else [x for x in entries if x["relative"] == choice or x["path"].name == choice]
        if not selected:
            raise RuntimeError(f"未找到指定 JSON 输入：{choice}")
        count = 0
        for entry in selected:
            objs = self._load_json_file(entry["path"])
            for obj in objs:
                self.state.pending_split.append(obj)
                count += 1
            self.state.register_loaded_source("json", entry["relative"], {"recognized": len(objs)})
        report = self._write_precheck(f"已载入 JSON：{choice}")
        print(f"已载入 JSON，候选要素 {count} 条。预校验报告：{report}")
        return {"summary": f"已载入 JSON {count} 条"}

    def do_load_image(self, arg):
        self.state.mode = "image"
        if not self.state.enter_manual_mode_if_needed():
            raise RuntimeError("当前 staging 为 package 独占模式，因此 load-image 不可用。")
        entries = self._scan_image_inputs()
        if not entries:
            print("未在 source_data/image_inputs 中找到图片文件。")
            return {"summary": "未发现图片输入"}
        choice = arg.strip() or "all"
        selected = entries if choice == "all" else [x for x in entries if x["relative"] == choice or x["path"].name == choice]
        if not selected:
            raise RuntimeError(f"未找到指定图片输入：{choice}")
        count = 0
        for entry in selected:
            item_id = self._auto_bind_image_to_existing(entry["path"])
            if not item_id:
                self.state.warnings.append(f"图片无法自动绑定，已跳过：{entry['relative']}")
                continue
            if any(x.get("id") == item_id for x in self.state.pending_delete):
                self.state.blocking.append(f"当前会话已将 ID 标记为删除，不能再载入图片：{item_id}")
                continue
            meta = self._lookup_feature_metadata(item_id)
            if not meta:
                self.state.warnings.append(f"未找到图片目标要素，已跳过：{entry['relative']}")
                continue
            self._register_picture_append(item_id, meta["world"], meta["class"], meta["kind"], entry["path"])
            self.state.register_loaded_source("image", entry["relative"], {"id": item_id})
            count += 1
        report = self._write_precheck(f"已载入图片：{choice}")
        print(f"已载入图片 {count} 张。预校验报告：{report}")
        return {"summary": f"已载入图片 {count} 张"}

    def _load_package_from_directory(self, package_dir: Path):
        index_path = package_dir / "INDEX.json"
        if self._policy("scan_policy", "package_require_index", True) and not index_path.exists():
            raise RuntimeError(f"标准包缺少 INDEX.json：{package_dir.name}")
        split_dir = package_dir / "Data_Spilt"
        picture_dir = package_dir / "Picture"
        delete_path = package_dir / "Delete.json"
        if self._policy("scan_policy", "package_require_split_dir", True) and not split_dir.exists():
            raise RuntimeError(f"标准包缺少 Data_Spilt：{package_dir.name}")
        if self._policy("scan_policy", "package_require_picture_dir", True) and not picture_dir.exists():
            raise RuntimeError(f"标准包缺少 Picture：{package_dir.name}")

        split_items = []
        id_seen = set()
        for p in split_dir.rglob("*.json"):
            if p.name == "INDEX.json":
                continue
            obj = read_json(p)
            if not isinstance(obj, dict):
                self.state.blocking.append(f"包内存在非法 JSON：{p}")
                continue
            brief = self._new_item_brief(obj)
            item_id = brief["id"]
            if not item_id:
                self.state.blocking.append(f"包内对象缺少 ID：{p}")
                continue
            if item_id in id_seen:
                self.state.blocking.append(f"包内重复 ID：{item_id}")
            id_seen.add(item_id)
            class_name = brief["class"]
            world = brief["world"]
            kind = brief["kind"]
            self._validate_schema_fields(class_name, kind)
            split_items.append({
                "id": item_id,
                "class": class_name,
                "world": world,
                "kind": kind,
                "obj": obj,
                "source": str(p),
            })

        picture_entries = []
        if picture_dir.exists():
            by_group: dict[tuple[str, str, str | None, str], list[Path]] = {}
            for p in picture_dir.rglob("*"):
                if p.is_dir() or p.name == "INDEX.json":
                    continue
                rel = p.relative_to(picture_dir).parts
                if len(rel) < 3:
                    self.state.warnings.append(f"包内图片路径无法识别：{p}")
                    continue
                world, class_name = rel[0], rel[1]
                idx = 2
                kind = None
                if self._is_special_class(class_name):
                    if len(rel) < 4:
                        self.state.blocking.append(f"特殊类图片路径非法：{p}")
                        continue
                    kind = rel[2]
                    idx = 3
                item_id = rel[idx]
                key = (world, class_name, kind, item_id)
                by_group.setdefault(key, []).append(p)
            for (world, class_name, kind, item_id), files in by_group.items():
                picture_entries.append({
                    "id": item_id,
                    "world": world,
                    "class": class_name,
                    "kind": kind,
                    "group_mode": "replace_group",
                    "files": [str(x) for x in sorted(files)],
                })

        delete_entries = []
        if delete_path.exists():
            raw = read_json(delete_path)
            items = raw.get("items", []) if isinstance(raw, dict) else []
            seen_delete = set()
            for item in items:
                item_id = normalize_text(get_field(item, "ID", "id"))
                if not item_id:
                    self.state.blocking.append("Delete.json 中存在缺少 ID 的项")
                    continue
                if item_id in seen_delete:
                    self.state.blocking.append(f"Delete.json 内重复 ID：{item_id}")
                seen_delete.add(item_id)
                delete_entries.append({"id": item_id, "raw": item})
                if item_id in id_seen:
                    self.state.blocking.append(f"包内同一 ID 同时出现在 Split 与 Delete：{item_id}")

        overwrite_existing = sum(1 for x in split_items if any(self.split_root.rglob(f"{x['id']}.json")))
        delete_missing = sum(1 for x in delete_entries if not any(self.split_root.rglob(f"{x['id']}.json")))
        return {
            "package_name": package_dir.name,
            "split_count": len(split_items),
            "picture_group_count": len(picture_entries),
            "picture_file_count": sum(len(x.get("files", [])) for x in picture_entries),
            "delete_count": len(delete_entries),
            "overwrite_existing_count": overwrite_existing,
            "delete_missing_count": delete_missing,
            "split_items": split_items,
            "picture_entries": picture_entries,
            "delete_entries": delete_entries,
        }

    def do_load_package(self, arg):
        self.state.mode = "package"
        if not self.state.enter_package_mode():
            raise RuntimeError("当前 staging 不为空，因此 load-package 不可用。")
        entries = self._scan_relay_packages()
        if not entries:
            print("未在 source_data/relay_packages 中找到标准包。")
            return {"summary": "未发现标准包"}
        choice = arg.strip()
        target = None
        if choice:
            for e in entries:
                if e["relative"] == choice or e["path"].name == choice:
                    target = e["path"]
                    break
        else:
            target = entries[0]["path"]
        if target is None:
            raise RuntimeError(f"未找到指定标准包：{choice}")
        temp_extracted = None
        temp_root = None
        if target.suffix.lower() == ".zip":
            temp_extracted = self._extract_package_zip(target)
            temp_root = temp_extracted.parent if temp_extracted.parent.name.startswith(target.stem) else temp_extracted
            self.state.register_temp_path(str(temp_root))
            load_target = temp_extracted
        else:
            load_target = target
        summary = self._load_package_from_directory(load_target)
        if temp_root:
            # 不能在这里提前删除 zip 解压临时目录。
            # package staging 中的图片文件路径仍引用该目录，
            # 必须等到 commit/discard/exit 时再统一清理。
            temp_root_str = str(temp_root)
            if temp_root_str not in self.state.current_temp_paths:
                self.state.register_temp_path(temp_root_str)
        self.state.pending_split.extend(summary["split_items"])
        self.state.pending_pictures.extend(summary["picture_entries"])
        self.state.pending_delete.extend(summary["delete_entries"])
        self.state.register_loaded_source("package", summary["package_name"], {
            "split_count": summary["split_count"],
            "picture_group_count": summary["picture_group_count"],
            "delete_count": summary["delete_count"],
            "overwrite_existing_count": summary.get("overwrite_existing_count", 0),
            "delete_missing_count": summary.get("delete_missing_count", 0),
        })
        if summary.get("overwrite_existing_count"):
            self.state.warnings.append(f"package 将覆盖已存在要素：{summary['overwrite_existing_count']} 项")
        if summary.get("delete_missing_count"):
            self.state.warnings.append(f"package 删除目标中有 {summary['delete_missing_count']} 项当前不存在")
        report = self._write_precheck(f"已载入 package：{summary['package_name']}")
        print(f"已载入标准包：{summary['package_name']}。预校验报告：{report}")
        return {"summary": f"已载入 package {summary['package_name']}"}

    # ---------- indexes ----------
    def _collect_leaf_jsons(self, leaf_dir: Path):
        return sorted([p for p in leaf_dir.glob("*.json") if p.name != "INDEX.json"])

    def _rebuild_leaf_index(self, leaf_dir: Path):
        files = self._collect_leaf_jsons(leaf_dir)
        data = {
            "version": 1,
            "updated": now_iso(),
            "count": len(files),
            "files": [p.name for p in files],
        }
        write_json(leaf_dir / "INDEX.json", data)

    def _rebuild_picture_leaf_index(self, leaf_dir: Path):
        files = sorted([p for p in leaf_dir.iterdir() if p.is_file() and p.name != "INDEX.json"])
        data = {
            "version": 1,
            "updated": now_iso(),
            "count": len(files),
            "files": [p.name for p in files],
        }
        write_json(leaf_dir / "INDEX.json", data)

    def _rebuild_merge_index(self, leaf_dir: Path, chunk_size: int):
        files = sorted([p for p in leaf_dir.glob("chunk_*.json")])
        data = {
            "version": 1,
            "updated": now_iso(),
            "count": len(files),
            "chunk_size": chunk_size,
            "files": [p.name for p in files],
        }
        write_json(leaf_dir / "INDEX.json", data)

    def _bump_root_index(self, root_dir: Path):
        count = sum(1 for p in root_dir.rglob("*.json") if p.name != "INDEX.json")
        write_json(root_dir / "INDEX.json", {"version": 1, "updated": now_iso(), "count": count})

    def _bump_world_index(self, root_dir: Path, world_dir_name: str):
        world_dir = root_dir / world_dir_name
        if world_dir.exists():
            count = sum(1 for p in world_dir.rglob("*.json") if p.name != "INDEX.json")
            write_json(world_dir / "INDEX.json", {"version": 1, "updated": now_iso(), "count": count})

    def _queue_rebuild_target(self, world, class_name, kind):
        self._append_unique(self.state.pending_merge, {"world": world, "class": class_name, "kind": kind}, key=lambda x: (str(x["world"]), x["class"], x.get("kind")))

    def _resolve_rebuild_targets(self, arg):
        if arg == "--all":
            targets = []
            for idx in self.split_root.rglob("INDEX.json"):
                if idx.parent == self.split_root:
                    continue
                rel = idx.parent.relative_to(self.split_root)
                parts = rel.parts
                if len(parts) < 2:
                    continue
                world, class_name = parts[0], parts[1]
                kind = parts[2] if self._is_special_class(class_name) and len(parts) >= 3 else None
                targets.append((world, class_name, kind))
            for world, class_name, kind in targets:
                self._queue_rebuild_target(world, class_name, kind)
            return len(targets)
        parts = arg.split()
        if len(parts) == 2:
            self._queue_rebuild_target(parts[0], parts[1], None)
            return 1
        if len(parts) == 3:
            self._queue_rebuild_target(parts[0], parts[1], parts[2])
            return 1
        self.state.blocking.append(f"rebuild 参数不合法：{arg}")
        return 0

    # ---------- preview/report/status ----------
    def do_preview(self, arg):
        print("当前 staging 摘要：")
        print(f"  staging_mode: {self.state.staging_mode}")
        print(f"  loaded_sources: {len(self.state.loaded_sources)}")
        print(f"  待写入 Split: {len(self.state.pending_split)}")
        print(f"  待写入图片: {len(self.state.pending_pictures)}")
        print(f"  待删除: {len(self.state.pending_delete)}")
        print(f"  待重建 Merge: {len(self.state.pending_merge)}")
        print(f"  warnings: {len(self.state.warnings)}")
        print(f"  blocking: {len(self.state.blocking)}")
        return {"summary": "已输出 staging 摘要"}

    def do_report(self, arg):
        candidates = [
            self.state.last_precheck_report_path,
            self.state.last_commit_report_path,
            self.state.last_push_report_path,
        ]
        for c in candidates:
            if c and Path(c).exists():
                print(Path(c).read_text(encoding="utf-8"))
                return {"summary": f"已显示报告 {Path(c).name}"}
        print("当前没有可显示的报告。")
        return {"summary": "无报告"}

    def do_status(self, arg):
        print("当前会话状态：")
        print(f"  mode: {self.state.mode or '-'}")
        print(f"  staging_mode: {self.state.staging_mode}")
        print(f"  待写入 Split 数量: {len(self.state.pending_split)}")
        print(f"  待写入图片数量: {len(self.state.pending_pictures)}")
        print(f"  待删除数量: {len(self.state.pending_delete)}")
        print(f"  待重建 Merge 数量: {len(self.state.pending_merge)}")
        print(f"  警告数量: {len(self.state.warnings)}")
        print(f"  阻断数量: {len(self.state.blocking)}")
        print(f"  当前 session_id: {self.state.session_id}")
        print(f"  当前 World 映射数量: {len(self.world_map)}")
        print(f"  当前特殊类数量: {len(self.special_class_set)}")
        return {"summary": "已输出 status"}

    # ---------- commit ----------
    def _commit_source(self):
        changed_split_dirs = set()
        changed_picture_dirs = set()
        changed_worlds = set()
        affected_classes = set()
        affected_kinds = set()
        split_count = picture_count = picture_group_replaced = delete_count = 0

        for item in self.state.pending_split:
            leaf = self._split_leaf_dir(item["world"], item["class"], item.get("kind"))
            ensure_dir(leaf)
            write_json(leaf / f"{item['id']}.json", item["obj"])
            changed_split_dirs.add(leaf)
            changed_worlds.add(self.resolve_world_dir_name(item["world"]))
            affected_classes.add(item["class"])
            if item.get("kind"):
                affected_kinds.add(item.get("kind"))
            split_count += 1

        for pic in self.state.pending_pictures:
            base = self._picture_leaf_dir(pic["world"], pic["class"], pic.get("kind")) / pic["id"]
            ensure_dir(base)
            if pic.get("group_mode") == "replace_group":
                if base.exists():
                    shutil.rmtree(base)
                ensure_dir(base)
                picture_group_replaced += 1
                idx = 1
                for src in pic.get("files", []):
                    src_path = Path(src)
                    dst = base / f"{pic['id']}_{idx}{src_path.suffix.lower()}"
                    shutil.copy2(src_path, dst)
                    idx += 1
                    picture_count += 1
            else:
                existing = sorted([p for p in base.iterdir() if p.is_file() and p.name != "INDEX.json"]) if base.exists() else []
                next_idx = len(existing) + 1
                for src in pic.get("files", []):
                    src_path = Path(src)
                    dst = base / f"{pic['id']}_{next_idx}{src_path.suffix.lower()}"
                    shutil.copy2(src_path, dst)
                    next_idx += 1
                    picture_count += 1
            self._rebuild_picture_leaf_index(base)
            changed_picture_dirs.add(base)

        for item in self.state.pending_delete:
            item_id = item["id"]
            removed = False
            for p in self.split_root.rglob(f"{item_id}.json"):
                p.unlink(missing_ok=True)
                removed = True
                changed_split_dirs.add(p.parent)
                if len(p.relative_to(self.split_root).parts) >= 2:
                    changed_worlds.add(p.relative_to(self.split_root).parts[0])
                    affected_classes.add(p.relative_to(self.split_root).parts[1])
            for p in self.picture_root.rglob(item_id):
                if p.is_dir():
                    shutil.rmtree(p)
                    removed = True
            if not removed:
                self.state.warnings.append(f"Delete 目标不存在：{item_id}")
            delete_count += 1

        for d in changed_split_dirs:
            ensure_dir(d)
            self._rebuild_leaf_index(d)
        for world_dir_name in sorted(changed_worlds):
            self._bump_world_index(self.split_root, world_dir_name)
            self._bump_world_index(self.picture_root, world_dir_name)
        if changed_split_dirs:
            self._bump_root_index(self.split_root)
        if changed_picture_dirs:
            self._bump_root_index(self.picture_root)

        return {
            "changed_split_dirs": changed_split_dirs,
            "changed_picture_dirs": changed_picture_dirs,
            "changed_worlds": changed_worlds,
            "affected_classes": affected_classes,
            "affected_kinds": affected_kinds,
            "split_written_count": split_count,
            "picture_written_count": picture_count,
            "picture_group_replaced_count": picture_group_replaced,
            "delete_count": delete_count,
        }

    def _commit_merge(self):
        chunk_size = int(self.tool_config.get("chunk_size", 200))
        changed_dirs = set()
        changed_worlds = set()
        affected_classes = set()
        affected_kinds = set()
        output_count = 0
        for target in self.state.pending_merge:
            leaf = self._split_leaf_dir(target["world"], target["class"], target.get("kind"))
            mleaf = self._merge_leaf_dir(target["world"], target["class"], target.get("kind"))
            ensure_dir(mleaf)
            for p in mleaf.glob("chunk_*.json"):
                p.unlink(missing_ok=True)
            items = []
            if leaf.exists():
                for p in self._collect_leaf_jsons(leaf):
                    try:
                        obj = read_json(p)
                        if isinstance(obj, dict):
                            items.append(obj)
                    except Exception:
                        self.state.warnings.append(f"重建时跳过非法 JSON：{p}")
            if items:
                for i in range(0, len(items), chunk_size):
                    fname = f"chunk_{(i // chunk_size) + 1:03d}.json"
                    write_json(mleaf / fname, items[i:i + chunk_size])
                    output_count += 1
            self._rebuild_merge_index(mleaf, chunk_size)
            changed_dirs.add(mleaf)
            changed_worlds.add(self.resolve_world_dir_name(target["world"]))
            affected_classes.add(target["class"])
            if target.get("kind"):
                affected_kinds.add(target.get("kind"))
        if changed_dirs:
            self._bump_root_index(self.merge_root)
            for world_dir_name in sorted(changed_worlds):
                self._bump_world_index(self.merge_root, world_dir_name)
        return {
            "changed_merge_dirs": changed_dirs,
            "changed_worlds": changed_worlds,
            "affected_classes": affected_classes,
            "affected_kinds": affected_kinds,
            "merge_target_count": len(self.state.pending_merge),
            "merge_output_file_count": output_count,
        }

    def do_commit(self, arg):
        source_pending = any([self.state.pending_split, self.state.pending_pictures, self.state.pending_delete])
        merge_pending = bool(self.state.pending_merge)
        source_stats = self._commit_source() if source_pending else {
            "changed_split_dirs": set(), "changed_picture_dirs": set(), "changed_worlds": set(), "affected_classes": set(), "affected_kinds": set(),
            "split_written_count": 0, "picture_written_count": 0, "picture_group_replaced_count": 0, "delete_count": 0,
        }
        merge_stats = self._commit_merge() if merge_pending else {
            "changed_merge_dirs": set(), "changed_worlds": set(), "affected_classes": set(), "affected_kinds": set(),
            "merge_target_count": 0, "merge_output_file_count": 0,
        }
        summary = {
            "source_committed": source_pending,
            "merge_committed": merge_pending,
            "split_written": source_stats["split_written_count"],
            "picture_written": source_stats["picture_written_count"],
            "picture_group_replaced": source_stats["picture_group_replaced_count"],
            "delete_applied": source_stats["delete_count"],
            "merge_targets": merge_stats["merge_target_count"],
            "merge_outputs_written": merge_stats["merge_output_file_count"],
            "affected_worlds": sorted({*source_stats["changed_worlds"], *merge_stats["changed_worlds"]}),
            "affected_classes": sorted({*source_stats["affected_classes"], *merge_stats["affected_classes"]}),
            "affected_kinds": sorted({*source_stats["affected_kinds"], *merge_stats["affected_kinds"]}),
            "staging_mode": self.state.staging_mode,
            "loaded_sources": list(self.state.loaded_sources),
        }
        lines = [
            "# 提交报告", "",
            f"时间：{now_iso()}",
            f"staging_mode：{self.state.staging_mode}",
            f"- Split：{summary['split_written']}",
            f"- 图片：{summary['picture_written']}",
            f"- 图片组替换：{summary['picture_group_replaced']}",
            f"- 删除：{summary['delete_applied']}",
            f"- Merge 目标：{summary['merge_targets']}",
            f"- Merge 输出文件：{summary['merge_outputs_written']}",
            f"- 受影响 World：{', '.join(summary['affected_worlds']) or '-'}",
            f"- 受影响 Class：{', '.join(summary['affected_classes']) or '-'}",
        ]
        latest, _ = self.report_manager.write_commit_report("\n".join(lines))
        self.state.last_commit_report_path = str(latest)
        commit_log_path = self.log_manager.write_commit_log(summary)
        self.state.register_commit_log(str(commit_log_path))
        self.state.last_commit_summary = summary
        self.state.last_commit_change_stats = {
            "split_dirs": len(source_stats["changed_split_dirs"]),
            "picture_dirs": len(source_stats["changed_picture_dirs"]),
            "merge_dirs": len(merge_stats["changed_merge_dirs"]),
        }
        for temp in list(self.state.current_temp_paths):
            try:
                tp = Path(temp)
                if tp.exists():
                    shutil.rmtree(tp, ignore_errors=True)
            except Exception:
                pass
        self.state.current_temp_paths = []
        self.state.clear()
        print(f"提交完成。报告：{latest}\ncommit log：{commit_log_path}")
        return {"summary": "commit 完成"}

    def do_rebuild(self, arg):
        self.state.mode = "rebuild"
        added = self._resolve_rebuild_targets(arg.strip())
        report = self._write_precheck(f"已登记 rebuild 目标：{arg.strip()}")
        print(f"已登记待重建目标 {added} 个。报告：{report}")
        return {"summary": f"已登记 rebuild {added} 个"}

    # ---------- sync web schema ----------
    def do_sync_web_schema(self, arg):
        schema_file = self.web_schema_source / "data_tool_schema.json"
        if schema_file.exists():
            schema = read_json(schema_file)
            worlds = schema.get("worlds", {})
            if isinstance(worlds, dict) and worlds:
                data = {"_comment": "由 data_tool_schema.json 自动解析生成。world code -> worldId 映射。"}
                for world_id, code in worlds.items():
                    data[str(code)] = str(world_id)
                write_json(self.world_map_path, data)
                self.world_map = {k: v for k, v in data.items() if not k.startswith("_")}
            feature_classes = schema.get("featureClasses", [])
            if isinstance(feature_classes, list):
                write_json(self.feature_classes_path, {"feature_classes": sorted([str(x) for x in feature_classes if str(x).strip()])})
                self.feature_class_set = self._load_feature_classes()
            special_classes = schema.get("specialClasses", [])
            if isinstance(special_classes, list):
                write_json(self.special_class_rules_path, {"special_classes": sorted([str(x) for x in special_classes if str(x).strip()])})
                self.special_class_set = self._load_special_classes()
            workflow_kinds = schema.get("workflowKinds", {})
            if isinstance(workflow_kinds, dict):
                write_json(self.workflow_kind_registry_path, {"workflow_kinds": workflow_kinds})
                self.workflow_kind_registry = self._load_workflow_kind_registry()
            print("schema 缓存已更新；当前 staging 中已载入内容保持不变。")
            return {"summary": "schema 已同步"}
        source_file = self.web_schema_source / "featureFormats.ts"
        if not source_file.exists():
            raise RuntimeError("未找到 web_schema/source/data_tool_schema.json 或 featureFormats.ts，无法同步。")
        text = source_file.read_text(encoding="utf-8")
        pairs = re.findall(r"(\w+)\s*:\s*(\d+)", text)
        if pairs:
            data = {str(code): world_id for world_id, code in pairs}
            write_json(self.world_map_path, data)
            self.world_map = data
        classes = re.findall(r'"(ISG|ISL|ISP)"', text)
        if classes:
            write_json(self.special_class_rules_path, {"special_classes": sorted(set(classes))})
            self.special_class_set = self._load_special_classes()
        print("schema 缓存已更新；当前 staging 中已载入内容保持不变。")
        return {"summary": "schema 已同步"}

    # ---------- env check ----------
    def do_check_env(self, arg):
        result = run_env_checks(self.repo_root, self.root, self.tool_config)
        lines = ["# 环境检查报告", "", f"时间：{now_iso()}", f"总结果：{result['overall']}", "", "## 明细"]
        for item in result["items"]:
            lines.append(f"- [{item['status']}] {item['name']}：{item['detail']}")
            print(f"[{item['status']}] {item['name']}：{item['detail']}")
        latest, _ = self.report_manager.write_env_check_report("\n".join(lines))
        self.state.last_precheck_report_path = str(latest)
        print(f"环境检查报告已输出：{latest}")
        return {"summary": f"环境检查 {result['overall']}"}

    # ---------- push helpers ----------
    def _ensure_env_ready_for_push(self):
        git_status_porcelain(self.repo_root)
        token_env = self.tool_config.get("github", {}).get("cold_token_env", "OPENRIAMAP_COLD_PAT")
        token = os.environ.get(token_env, "")
        if not token:
            raise RuntimeError(f"缺少环境变量 {token_env}")
        return token

    def _ensure_env_ready_for_data_push(self):
        git_status_porcelain(self.repo_root)
        return True

    def _build_archive_manifest(self, source_summary: dict, log_summary: dict):
        head = ""
        try:
            head = get_git_head_hash(self.repo_root)
        except Exception:
            head = ""
        return {
            "tool_version": TOOL_VERSION,
            "session_id": self.state.session_id,
            "created_at": now_iso(),
            "repo_head_before_push": head,
            "source_data": source_summary,
            "logs": log_summary,
            "last_commit_summary": self.state.last_commit_summary,
            "last_commit_change_stats": self.state.last_commit_change_stats,
        }

    def _collect_runtime_logs_for_archive(self, archive_ctx: dict):
        copied = []
        to_delete = []
        candidates = []
        if self.state.current_session_log_path:
            candidates.append(Path(self.state.current_session_log_path))
        candidates.extend(Path(x) for x in self.state.current_commit_log_paths)
        for path in candidates:
            if not path.exists():
                continue
            target = archive_ctx["logs_root"] / path.name
            shutil.copy2(path, target)
            copied.append(path)
            to_delete.append(path)
        return {
            "copied_count": len(copied),
            "copied_paths": [str(x) for x in copied],
            "to_delete_after_success": to_delete,
        }

    def _resolve_remote_asset_name(self, release_id: int, base_name: str, token: str):
        repo = self.tool_config.get("github", {}).get("cold_repo", "OpenRIAMap/ColdToolArchive")
        assets = list_release_assets(repo, release_id, token)
        existing = {a.get("name") for a in assets}
        stem = Path(base_name).stem
        suffix = Path(base_name).suffix
        candidate = base_name
        idx = 0
        while candidate in existing:
            idx += 1
            candidate = f"{stem}_{idx}{suffix}"
        return candidate

    def _verify_remote_asset(self, release_id: int, asset_name: str, expected_size: int, token: str):
        repo = self.tool_config.get("github", {}).get("cold_repo", "OpenRIAMap/ColdToolArchive")
        asset = find_release_asset(repo, release_id, token, asset_name)
        if not asset:
            raise RuntimeError(f"冷仓库资产校验失败：未找到 {asset_name}")
        if int(asset.get("size", -1)) != int(expected_size):
            raise RuntimeError("冷仓库资产校验失败：大小不一致")
        return asset

    def _count_repo_files_snapshot(self):
        result = {"total_files": 0}
        for root_name in ["Data_Spilt", "Data_Merge", "Picture", str(Path("Data_Merge_Tool") / "logs" / "push")]:
            path = self.repo_root / root_name
            count = sum(1 for p in path.rglob("*") if p.is_file()) if path.exists() else 0
            result[root_name.replace('/', '_')] = count
            result["total_files"] += count
        return result

    def _build_data_repo_commit_message(self, cold_archive_summary: dict | None = None):
        ts = datetime.now(TZ_8).strftime("%Y-%m-%d %H:%M")
        summary = self.state.last_commit_summary or {}
        split_n = summary.get("split_written", 0)
        pic_n = summary.get("picture_written", 0)
        merge_n = summary.get("merge_outputs_written", 0)
        archive_n = 1 if cold_archive_summary else 0
        return f"数据仓库更新：新增/覆盖数据、重建 Merge、写入归档日志（{ts}）[Split {split_n} | Picture {pic_n} | Merge {merge_n} | Archive {archive_n}]"

    def _cleanup_local_runtime_after_cold_push(self, archive_ctx: dict, archive_zip: Path | None, log_summary: dict):
        warnings = []
        deleted = []
        try:
            if self.tool_config.get("push", {}).get("clean_source_data_after_push", True):
                for sub in ["json_inputs", "image_inputs", "relay_packages"]:
                    d = self.source_data / sub
                    if d.exists():
                        for item in d.iterdir():
                            if item.name.startswith('.gitkeep'):
                                continue
                            try:
                                if item.is_dir():
                                    shutil.rmtree(item)
                                else:
                                    item.unlink(missing_ok=True)
                                deleted.append(str(item))
                            except Exception as e:
                                warnings.append(f"删除 source_data 失败：{item} -> {e}")
                        (d / '.gitkeep').write_text('', encoding='utf-8')
            if self.tool_config.get("push", {}).get("clean_workspace_after_push", True):
                for p in [archive_ctx.get("root")]:
                    if p and Path(p).exists():
                        shutil.rmtree(p, ignore_errors=True)
                        deleted.append(str(p))
            if archive_zip and archive_zip.exists():
                archive_zip.unlink(missing_ok=True)
                deleted.append(str(archive_zip))
            latest_reports = self.reports_root / "latest"
            if latest_reports.exists():
                for p in latest_reports.glob("*.md"):
                    p.unlink(missing_ok=True)
                    deleted.append(str(p))
                (latest_reports / '.gitkeep').write_text('', encoding='utf-8')
            for p in log_summary.get("to_delete_after_success", []):
                try:
                    Path(p).unlink(missing_ok=True)
                    deleted.append(str(p))
                except Exception as e:
                    warnings.append(f"删除日志失败：{p} -> {e}")
            self.state.current_commit_log_paths = [x for x in self.state.current_commit_log_paths if x not in {str(p) for p in log_summary.get('to_delete_after_success', [])}]
        except Exception as e:
            warnings.append(str(e))
        return {"deleted_paths": deleted, "warnings": warnings}

    def do_push_cold(self, arg):
        token = self._ensure_env_ready_for_push()
        state = "P0"
        archive_ctx = None
        archive_zip = None
        try:
            state = "P1"
            archive_ctx = prepare_archive_workspace(self.workspace)
            source_summary = {
                "json_inputs": copy_tree_contents(self.source_data / "json_inputs", archive_ctx["source_data_root"] / "json_inputs"),
                "image_inputs": copy_tree_contents(self.source_data / "image_inputs", archive_ctx["source_data_root"] / "image_inputs"),
                "relay_packages": copy_tree_contents(self.source_data / "relay_packages", archive_ctx["source_data_root"] / "relay_packages"),
            }
            log_summary = self._collect_runtime_logs_for_archive(archive_ctx)
            manifest = self._build_archive_manifest(source_summary, log_summary)
            write_manifest(archive_ctx["archive_root"], manifest)
            state = "P2"
            base_name = f"OpenRIAMap_DataTool_Archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            archive_zip = build_zip(archive_ctx["archive_root"], archive_ctx["root"], base_name)
            state = "P3"
            repo_name = self.tool_config.get("github", {}).get("cold_repo", "OpenRIAMap/ColdToolArchive")
            month_tag = datetime.now(TZ_8).strftime("%Y-%m")
            release = ensure_monthly_release(repo_name, token, month_tag, f"Cold Archive {month_tag}")
            asset_name = self._resolve_remote_asset_name(release["id"], archive_zip.name, token)
            if asset_name != archive_zip.name:
                new_path = archive_zip.with_name(asset_name)
                archive_zip.rename(new_path)
                archive_zip = new_path
            upload = upload_release_asset(release["upload_url"], token, archive_zip, archive_zip.name)
            state = "P4"
            verified = self._verify_remote_asset(release["id"], archive_zip.name, archive_zip.stat().st_size, token)
            state = "P5"
            cleanup = self._cleanup_local_runtime_after_cold_push(archive_ctx, archive_zip, log_summary)
            summary = {
                "mode": "cold_only",
                "state": state,
                "cold_success": True,
                "cold_repo": repo_name,
                "release_tag": month_tag,
                "asset_name": archive_zip.name,
                "asset_url": verified.get("browser_download_url") or upload.get("browser_download_url", ""),
                "cleanup_warnings": cleanup.get("warnings", []),
            }
            push_log = self.log_manager.write_push_log(summary)
            self.state.register_push_log(str(push_log))
            self.state.last_push_summary = summary
            latest, _ = self.report_manager.write_push_report("\n".join([
                "# Push 报告",
                "",
                f"时间：{now_iso()}",
                "模式：cold_only",
                f"冷仓库：{repo_name}",
                f"Release：{month_tag}",
                f"Asset：{archive_zip.name}",
                f"清理警告：{'; '.join(cleanup.get('warnings', [])) or '无'}",
            ]))
            self.state.last_push_report_path = str(latest)
            print(f"冷存储归档完成。push log：{push_log}")
            return {"summary": "push-cold 完成"}
        except Exception as e:
            if state in {"P1", "P2"} and archive_ctx:
                shutil.rmtree(archive_ctx["root"], ignore_errors=True)
                print("push 执行失败：归档准备/打包阶段出错，已恢复到执行前状态。")
            elif state in {"P3", "P4"}:
                if archive_ctx:
                    shutil.rmtree(archive_ctx["root"], ignore_errors=True)
                print("push 执行失败：冷存储上传或校验未通过。本地已执行恢复；如远端产生异常资产，请人工检查冷仓库。")
            raise RuntimeError(str(e))

    def do_push_data(self, arg):
        before = self._count_repo_files_snapshot()
        git_add_all(self.repo_root)
        message = self._build_data_repo_commit_message(None)
        commit_hash = git_commit(self.repo_root, message)
        git_pull_rebase(self.repo_root, self.tool_config["github"]["data_remote_name"], self.tool_config["github"]["data_branch"])
        git_push(self.repo_root, self.tool_config["github"]["data_remote_name"], self.tool_config["github"]["data_branch"])
        after = self._count_repo_files_snapshot()
        summary = {
            "mode": "data_only",
            "message": message,
            "commit_hash": commit_hash or get_git_head_hash(self.repo_root),
            "before": before,
            "after": after,
        }
        push_log = self.log_manager.write_push_log(summary)
        push_report = [
            "# Push 报告", "",
            f"时间：{now_iso()}",
            f"模式：data_only",
            f"commit：{summary['commit_hash']}",
            f"message：{message}",
        ]
        latest, _ = self.report_manager.write_push_report("\n".join(push_report))
        self.state.last_push_report_path = str(latest)
        print(f"Data 仓库 push 完成。push log：{push_log}")
        return {"summary": "push-data 完成"}

    def do_push(self, arg):
        token = self._ensure_env_ready_for_push()
        state = "P0"
        archive_ctx = None
        archive_zip = None
        cleanup = {"warnings": []}
        cold_summary = None
        try:
            state = "P1"
            archive_ctx = prepare_archive_workspace(self.workspace)
            source_summary = {
                "json_inputs": copy_tree_contents(self.source_data / "json_inputs", archive_ctx["source_data_root"] / "json_inputs"),
                "image_inputs": copy_tree_contents(self.source_data / "image_inputs", archive_ctx["source_data_root"] / "image_inputs"),
                "relay_packages": copy_tree_contents(self.source_data / "relay_packages", archive_ctx["source_data_root"] / "relay_packages"),
            }
            log_summary = self._collect_runtime_logs_for_archive(archive_ctx)
            manifest = self._build_archive_manifest(source_summary, log_summary)
            write_manifest(archive_ctx["archive_root"], manifest)
            state = "P2"
            archive_zip = build_zip(archive_ctx["archive_root"], archive_ctx["root"], f"OpenRIAMap_DataTool_Archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
            state = "P3"
            repo_name = self.tool_config.get("github", {}).get("cold_repo", "OpenRIAMap/ColdToolArchive")
            month_tag = datetime.now(TZ_8).strftime("%Y-%m")
            release = ensure_monthly_release(repo_name, token, month_tag, f"Cold Archive {month_tag}")
            asset_name = self._resolve_remote_asset_name(release["id"], archive_zip.name, token)
            if asset_name != archive_zip.name:
                new_path = archive_zip.with_name(asset_name)
                archive_zip.rename(new_path)
                archive_zip = new_path
            upload = upload_release_asset(release["upload_url"], token, archive_zip, archive_zip.name)
            state = "P4"
            verified = self._verify_remote_asset(release["id"], archive_zip.name, archive_zip.stat().st_size, token)
            cold_summary = {
                "cold_repo": repo_name,
                "release_tag": month_tag,
                "asset_name": archive_zip.name,
                "asset_url": verified.get("browser_download_url") or upload.get("browser_download_url", ""),
            }
            state = "P5"
            cleanup = self._cleanup_local_runtime_after_cold_push(archive_ctx, archive_zip, log_summary)
            state = "P6"
            before = self._count_repo_files_snapshot()
            git_add_all(self.repo_root)
            message = self._build_data_repo_commit_message(cold_summary)
            commit_hash = git_commit(self.repo_root, message)
            state = "P7"
            git_pull_rebase(self.repo_root, self.tool_config["github"]["data_remote_name"], self.tool_config["github"]["data_branch"])
            state = "P8"
            git_push(self.repo_root, self.tool_config["github"]["data_remote_name"], self.tool_config["github"]["data_branch"])
            after = self._count_repo_files_snapshot()
            state = "P9"
            summary = {
                "mode": "full",
                "cold_archive": cold_summary,
                "before": before,
                "after": after,
                "commit_hash": commit_hash or get_git_head_hash(self.repo_root),
                "message": message,
                "cleanup_warnings": cleanup.get("warnings", []),
                "state": state,
            }
            push_log = self.log_manager.write_push_log(summary)
            self.state.register_push_log(str(push_log))
            report_lines = [
                "# Push 报告", "",
                f"时间：{now_iso()}",
                f"模式：full",
                f"冷仓库：{cold_summary['cold_repo']}",
                f"Release：{cold_summary['release_tag']}",
                f"Asset：{cold_summary['asset_name']}",
                f"commit：{summary['commit_hash']}",
                f"message：{message}",
                f"清理警告：{'; '.join(cleanup.get('warnings', [])) or '无'}",
            ]
            latest, _ = self.report_manager.write_push_report("\n".join(report_lines))
            self.state.last_push_report_path = str(latest)
            print(f"push 完成。push log：{push_log}")
            if cleanup.get("warnings"):
                print("push 已完成，但本地运行产物清理存在警告，请查看 push log。")
            return {"summary": "push 完成"}
        except Exception as e:
            if state in {"P1", "P2"}:
                if archive_ctx:
                    shutil.rmtree(archive_ctx["root"], ignore_errors=True)
                print("push 执行失败，已恢复到执行前状态。")
            elif state in {"P3", "P4"}:
                if archive_ctx:
                    shutil.rmtree(archive_ctx["root"], ignore_errors=True)
                print("push 执行失败：冷存储阶段出错。本地已恢复；如远端存在异常资产，请人工检查。")
            elif state in {"P6", "P7", "P8", "P9"}:
                print("冷存储归档已完成，但 Data 仓库后续流程失败。请检查当前 git 状态并执行 push-data。")
            raise RuntimeError(str(e))

    # ---------- clear/discard/help/exit ----------
    def do_discard(self, arg):
        for temp in list(self.state.current_temp_paths):
            try:
                tp = Path(temp)
                if tp.exists():
                    shutil.rmtree(tp, ignore_errors=True)
            except Exception:
                pass
        self.state.current_temp_paths = []
        self.state.clear()
        print("当前 staging 已丢弃；会话记录继续保留。")
        return {"summary": "已 discard"}

    def do_clear(self, arg):
        self.state.clear_command_context()
        print("当前命令上下文已清空；当前 staging 与会话记录保持不变。")
        return {"summary": "已 clear command context"}

    def do_help(self, arg):
        print("可用命令：")
        for cmd_name in VALID_COMMANDS:
            print(f"  {cmd_name:<15} ({COMMAND_ALIASES[cmd_name]})")
        print("说明：load-json/load-image 支持手动叠加 staging；load-package 为独占模式。")
        return {"summary": "已显示 help"}

    def do_exit(self, arg):
        if self.state.has_pending_changes():
            print("工具退出：当前仍存在未提交的 staging 内容，本次会话日志已保留。")
        else:
            print("正在退出工具。")
        # 退出前清理 package zip 解压产生的临时目录，避免 workspace 残留。
        for temp in list(self.state.current_temp_paths):
            try:
                tp = Path(temp)
                if tp.exists():
                    shutil.rmtree(tp, ignore_errors=True)
            except Exception:
                pass
        self.state.current_temp_paths = []
        return True


if __name__ == "__main__":
    ToolShell().cmdloop()
