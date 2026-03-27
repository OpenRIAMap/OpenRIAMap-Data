from __future__ import annotations
import cmd
import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
TOOL_CONFIG_PATH = CONFIG_DIR / "tool_config.json"
POLICY_CONFIG_PATH = CONFIG_DIR / "policy_config.json"

VALID_COMMANDS = [
    "help", "status", "load-package", "load-json", "load-image",
    "preview", "report", "commit", "rebuild", "discard", "clear",
    "sync-web-schema", "exit"
]
TZ_8 = timezone(timedelta(hours=8))
INVALID_WINDOWS_CHARS = set('\\/:*?"<>|')


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
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1,10)} | {f"LPT{i}" for i in range(1,10)}
    if upper in reserved:
        return False, f"为 Windows 保留名: {value}"
    return True, ""


class SessionState:
    def __init__(self) -> None:
        self.mode = None
        self.pending_split = []
        self.pending_pictures = []
        self.pending_delete = []
        self.pending_merge = []
        self.warnings = []
        self.blocking = []
        self.last_report = None
        self.session_dir = None
        self.stats = {
            "json_total_objects": 0,
            "json_recognized_objects": 0,
            "json_skipped_objects": 0,
            "json_duplicate_ids": 0,
        }
        self.conflict_details = {}

    def clear(self) -> None:
        self.__init__()


class ToolShell(cmd.Cmd):
    intro = "OpenRIAMap 数据维护工具 v2（World 映射 / 冲突报告 / 进度提示版）\n输入 help 查看命令说明。"
    prompt = "> "

    def __init__(self) -> None:
        super().__init__()
        self.tool_config = read_json(TOOL_CONFIG_PATH)
        self.policy = read_json(POLICY_CONFIG_PATH)
        self.root = ROOT
        self.source_data = self.root / self.tool_config["paths"]["source_data"]
        self.workspace = self.root / self.tool_config["paths"]["workspace"]
        self.logs = self.root / self.tool_config["paths"]["logs"]
        self.web_schema_root = self.root / self.tool_config["paths"]["web_schema"]
        self.web_schema_source = self.web_schema_root / "source"
        self.web_schema_cache = self.web_schema_root / "cache"
        ensure_dir(self.source_data)
        ensure_dir(self.workspace)
        ensure_dir(self.logs)
        ensure_dir(self.web_schema_source)
        ensure_dir(self.web_schema_cache)
        self.repo_root = (self.root / self.tool_config["repository_root"]).resolve()
        self.world_map_path = self.web_schema_cache / "world_map.json"
        self.special_class_rules_path = self.web_schema_cache / "special_class_rules.json"
        self.world_map = self._load_world_map()
        self.special_class_set = self._load_special_classes()
        self.state = SessionState()

    @property
    def split_root(self):
        return self.repo_root / "Data_Spilt"

    @property
    def merge_root(self):
        return self.repo_root / "Data_Merge"

    @property
    def picture_root(self):
        return self.repo_root / "Picture"

    def _policy(self, section, key, default=None):
        return self.policy.get(section, {}).get(key, default)

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

    def _new_session(self):
        session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir = self.workspace / session_name
        for p in [
            session_dir / "source_staging",
            session_dir / "merge_staging",
            session_dir / "reports",
            session_dir / "meta",
        ]:
            ensure_dir(p)
        self.state.session_dir = session_dir

    def _write_report(self, name, text):
        if not self.state.session_dir:
            self._new_session()
        report_path = self.state.session_dir / "reports" / name
        report_path.write_text(text, encoding="utf-8")
        self.state.last_report = report_path
        (self.logs / name).write_text(text, encoding="utf-8")
        return report_path

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

    def _is_special_class(self, class_name):
        return class_name in self.special_class_set

    def _separator_line(self, title):
        style = self._policy("progress_policy", "separator_style", "arrow")
        if style == "arrow":
            return f"<---------------------- {title} ---------------------->"
        if style == "hash":
            return f"###################### {title} ######################"
        return f"====================== {title} ======================"

    def print_section(self, title):
        if self._policy("progress_policy", "enable_separator", True):
            print(self._separator_line(title))

    def print_progress(self, current, total, message):
        if self._policy("progress_policy", "enable_progress_output", True):
            print(f"[{current}/{total}] {message}")

    def _apply_severity(self, severity, message):
        if severity == "blocking":
            self.state.blocking.append(message)
        else:
            self.state.warnings.append(message)

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

    def _build_precheck_report(self, title):
        lines = [
            "# 预校验报告", "",
            f"时间：{now_iso()}",
            f"说明：{title}", "",
            "## 摘要",
            f"- 模式：{self.state.mode or '-'}",
            f"- 待写入 Split：{len(self.state.pending_split)}",
            f"- 待写入图片：{len(self.state.pending_pictures)}",
            f"- 待删除：{len(self.state.pending_delete)}",
            f"- 待重建 Merge：{len(self.state.pending_merge)}",
            f"- 警告：{len(self.state.warnings)}",
            f"- 阻断：{len(self.state.blocking)}",
        ]
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

        if self._policy("report_policy", "include_conflict_details", True) and self.state.conflict_details:
            lines += ["", "## JSON ID 冲突详情"]
            for fid, items in sorted(self.state.conflict_details.items()):
                lines.append(f"- ID: {fid}")
                seen = set()
                for item in items:
                    tup = (str(item.get("world")), item.get("class"), item.get("kind"), item.get("source"))
                    if tup in seen:
                        continue
                    seen.add(tup)
                    lines.append(f"  - World: {item.get('world')} | Class: {item.get('class')} | Kind: {item.get('kind') or '-'} | Source: {item.get('source')}")
        return "\n".join(lines)

    def _rebuild_split_index(self, leaf_dir):
        items = sorted([p.stem for p in leaf_dir.glob("*.json") if p.name != "INDEX.json"])
        idx_path = leaf_dir / "INDEX.json"
        version = 1
        if idx_path.exists():
            try:
                version = int(read_json(idx_path).get("version", 0)) + 1
            except Exception:
                pass
        write_json(idx_path, {"version": version, "itemCount": len(items), "updatedAt": now_iso(), "items": items})

    def _rebuild_picture_index(self, leaf_dir):
        mapping = {}
        if leaf_dir.exists():
            for id_dir in sorted([p for p in leaf_dir.iterdir() if p.is_dir()]):
                files = sorted([f"{id_dir.name}/{x.name}" for x in id_dir.iterdir() if x.is_file()])
                if files:
                    mapping[id_dir.name] = files
        idx_path = leaf_dir / "INDEX.json"
        version = 1
        if idx_path.exists():
            try:
                version = int(read_json(idx_path).get("version", 0)) + 1
            except Exception:
                pass
        write_json(idx_path, {"version": version, "itemCount": len(mapping), "updatedAt": now_iso(), "mapping": mapping})

    def _rebuild_merge_index(self, leaf_dir, chunk_size):
        chunk_files = sorted([p for p in leaf_dir.glob("chunk_*.json") if p.is_file()])
        items, chunks_meta = [], []
        for p in chunk_files:
            try:
                arr = read_json(p)
            except Exception:
                arr = []
            if not isinstance(arr, list):
                arr = []
            citems = []
            for obj in arr:
                if isinstance(obj, dict) and get_field(obj, "ID") is not None:
                    citems.append(str(get_field(obj, "ID")))
            citems = sorted(citems)
            items.extend(citems)
            chunks_meta.append({"file": p.name, "itemCount": len(citems), "items": citems})
        idx_path = leaf_dir / "INDEX.json"
        version = 1
        if idx_path.exists():
            try:
                version = int(read_json(idx_path).get("version", 0)) + 1
            except Exception:
                pass
        write_json(idx_path, {
            "version": version,
            "itemCount": len(items),
            "updatedAt": now_iso(),
            "items": sorted(items),
            "chunkSize": chunk_size,
            "chunkCount": len(chunk_files),
            "chunks": chunks_meta,
        })

    def _bump_world_index(self, root_dir, world_dir_name):
        """
        更新 world 层级 INDEX.json，仅记录 version 和 updatedAt。
        适用目录：
        - Data_Spilt/{world}/INDEX.json
        - Data_Merge/{world}/INDEX.json
        - Picture/{world}/INDEX.json
        """
        world_dir = root_dir / str(world_dir_name)
        ensure_dir(world_dir)
        idx_path = world_dir / "INDEX.json"
        version = 1
        if idx_path.exists():
            try:
                version = int(read_json(idx_path).get("version", 0)) + 1
            except Exception:
                version = 1
        write_json(idx_path, {"version": version, "updatedAt": now_iso()})

    def _bump_root_index(self, root_dir):
        idx_path = root_dir / "INDEX.json"
        version = 1
        if idx_path.exists():
            try:
                version = int(read_json(idx_path).get("version", 0)) + 1
            except Exception:
                pass
        write_json(idx_path, {"version": version, "updatedAt": now_iso()})

    def _find_feature_by_id(self, fid):
        matches = list(self.split_root.rglob(f"{fid}.json"))
        if not matches:
            return None
        p = matches[0]
        rel = p.relative_to(self.split_root)
        parts = rel.parts
        if len(parts) < 3:
            return None
        world, class_name = parts[0], parts[1]
        kind = parts[2] if self._is_special_class(class_name) and len(parts) >= 4 else None
        try:
            data = read_json(p)
        except Exception:
            data = {}
        return {"path": p, "world": world, "class": class_name, "kind": kind, "data": data or {}}

    def _find_by_indexes(self, fid):
        for idx in self.split_root.rglob("INDEX.json"):
            if idx.parent == self.split_root:
                continue
            try:
                data = read_json(idx)
            except Exception:
                continue
            items = data.get("items", [])
            if fid not in items:
                continue
            rel = idx.parent.relative_to(self.split_root)
            parts = rel.parts
            if len(parts) < 2:
                continue
            world, class_name = parts[0], parts[1]
            kind = parts[2] if self._is_special_class(class_name) and len(parts) >= 3 else None
            return {"world": world, "class": class_name, "kind": kind}
        return None

    def _candidate_id_from_image_name(self, filename):
        if not self._policy("image_binding_policy", "enable_auto_bind_by_suffix", True):
            return None
        stem = Path(filename).stem
        m = re.match(r"^(.*)_([0-9]+)$", stem)
        return m.group(1) if m else None

    def _recursive_json_files(self):
        base = self.source_data / "json_inputs"
        return sorted([p for p in (base.rglob("*.json") if self._policy("scan_policy", "recursive_json_scan", True) else base.glob("*.json")) if p.is_file()])

    def _recursive_image_files(self):
        base = self.source_data / "image_inputs"
        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
        iterator = base.rglob("*") if self._policy("scan_policy", "recursive_image_scan", True) else base.glob("*")
        return sorted([p for p in iterator if p.is_file() and p.suffix.lower() in exts])

    def _recursive_package_dirs(self):
        base = self.source_data / "relay_packages"
        iterator = base.rglob("*") if self._policy("scan_policy", "recursive_package_scan", True) else base.glob("*")
        results = []
        for p in iterator:
            if not p.is_dir():
                continue
            if self._policy("scan_policy", "package_require_index", True) and not (p / "INDEX.json").exists():
                continue
            if self._policy("scan_policy", "package_require_split_dir", True) and not (p / "Data_Spilt").exists():
                continue
            if self._policy("scan_policy", "package_require_picture_dir", True) and not (p / "Picture").exists():
                continue
            results.append(p)
        return sorted(results)

    def _register_conflict(self, fid, world, class_name, kind, source):
        self.state.conflict_details.setdefault(fid, [])
        self.state.conflict_details[fid].append({
            "world": world, "class": class_name, "kind": kind, "source": source
        })

    def _parse_json_file(self, target):
        try:
            data = read_json(target)
        except Exception as e:
            self.state.blocking.append(f"JSON 解析失败：{target.name} -> {e}")
            return
        items = data if isinstance(data, list) else (data.get("items") if isinstance(data, dict) else None)
        if not isinstance(items, list):
            self.state.blocking.append(f"JSON 顶层结构不受支持：{target.name}")
            return
        for obj in items:
            self.state.stats["json_total_objects"] += 1
            if not isinstance(obj, dict):
                self.state.stats["json_skipped_objects"] += 1
                self.state.blocking.append(f"检测到非对象型要素：{target.name}")
                continue
            fid = normalize_text(get_field(obj, "ID", "id"))
            class_name = normalize_text(get_field(obj, "Class", "class"))
            world = get_field(obj, "World", "world")
            kind = normalize_text(get_field(obj, "Kind", "kind"))
            if fid is None:
                self.state.stats["json_skipped_objects"] += 1
                self.state.blocking.append(f"存在缺失 ID 的要素：{target.name}")
                continue
            ok, reason = is_safe_filename_component(fid)
            if not ok:
                self.state.stats["json_skipped_objects"] += 1
                self._apply_severity(self._policy("conflict_policy", "invalid_id", "blocking"), f"非法 ID：{fid}（{reason}，来源 {target.name}）")
                continue
            if class_name is None:
                self.state.stats["json_skipped_objects"] += 1
                self.state.blocking.append(f"要素 {fid} 缺失 Class：{target.name}")
                continue
            if world is None:
                self.state.stats["json_skipped_objects"] += 1
                self._apply_severity(self._policy("conflict_policy", "missing_world", "blocking"), f"要素 {fid} 缺失 World：{target.name}")
                continue
            if self._is_special_class(class_name) and kind is None:
                self.state.stats["json_skipped_objects"] += 1
                self._apply_severity(self._policy("conflict_policy", "missing_kind_for_special_class", "blocking"), f"特殊类要素 {fid} 缺失 Kind：{target.name}")
                continue

            item = {"id": fid, "world": world, "class": class_name, "kind": kind, "data": obj, "source": str(target)}
            existing = next((x for x in self.state.pending_split if x["id"] == fid), None)
            if existing is None:
                self.state.pending_split.append(item)
                self.state.stats["json_recognized_objects"] += 1
            else:
                self.state.stats["json_duplicate_ids"] += 1
                same_structure = str(existing.get("world")) == str(world) and existing.get("class") == class_name and (existing.get("kind") or "") == (kind or "")
                sev = self._policy("conflict_policy", "duplicate_same_structure" if same_structure else "duplicate_cross_structure", "warning")
                self._register_conflict(fid, existing.get("world"), existing.get("class"), existing.get("kind"), existing.get("source"))
                self._register_conflict(fid, world, class_name, kind, str(target))
                self._apply_severity(sev, f"检测到重复 ID：{fid}（来源 {target.name}）")

    def _load_json(self):
        self.state.clear(); self._new_session(); self.state.mode = "json"
        files = self._recursive_json_files()
        base = self.source_data / "json_inputs"
        if not files:
            print("未在 source_data/json_inputs 及其子目录中发现 JSON 文件。"); return
        self.print_section("load-json")
        print("可用 JSON 文件：")
        for i, p in enumerate(files, 1):
            rel = p.relative_to(base) if self._policy("progress_policy", "show_relative_path", True) else p.name
            print(f"  {i}. {rel}")
        print("  all. 全部加载")
        choice = input("请输入要读取的 JSON 序号，或输入 all: ").strip().lower()
        if choice == "all":
            total = len(files)
            for i, target in enumerate(files, 1):
                rel = target.relative_to(base) if self._policy("progress_policy", "show_relative_path", True) else target.name
                self.print_progress(i, total, f"正在读取 JSON: {rel}")
                self._parse_json_file(target)
            self._write_report("precheck_report.md", self._build_precheck_report("已读取全部 JSON 文件"))
            print(f"已读取全部 JSON 文件，共 {len(files)} 个，识别到 {self.state.stats['json_recognized_objects']} 个候选要素。")
            self.print_section("load-json done"); return
        try:
            target = files[int(choice)-1]
        except Exception:
            print("输入无效。"); return
        self.print_progress(1,1, f"正在读取 JSON: {target.relative_to(base)}")
        self._parse_json_file(target)
        self._write_report("precheck_report.md", self._build_precheck_report(f"已读取 JSON：{target.relative_to(base)}"))
        print(f"已读取 JSON：{target.relative_to(base)}，识别到 {self.state.stats['json_recognized_objects']} 个候选要素。")
        self.print_section("load-json done")

    def _load_single_image_manual(self, target):
        fid = input(f"图片 {target.name} -> 请输入目标要素 ID: ").strip()
        if not fid:
            self.state.blocking.append(f"图片 {target.name} 未提供目标 ID。"); return
        ok, reason = is_safe_filename_component(fid)
        if not ok:
            self.state.blocking.append(f"图片目标 ID 非法：{fid}（{reason}）"); return
        found = self._find_feature_by_id(fid)
        if not found:
            self.state.blocking.append(f"目标要素不存在：{fid}"); return
        name_label = normalize_text(get_field(found["data"], "Name", "Label", "name", "label")) or "-"
        pic_leaf = self._picture_leaf_dir(found["world"], found["class"], found["kind"]) / fid
        existing = len([x for x in pic_leaf.iterdir() if x.is_file()]) if pic_leaf.exists() else 0
        print("目标要素确认信息：")
        print(f"  ID: {fid}")
        print(f"  World: {found['world']}")
        print(f"  Class: {found['class']}")
        print(f"  Kind: {found['kind'] or '-'}")
        print(f"  Name/Label: {name_label}")
        print(f"  Existing pictures: {existing}")
        if input("是否继续导入该图片？(yes/no): ").strip().lower() != "yes":
            self.state.warnings.append(f"图片已跳过：{target.name}"); return
        item = {"source": str(target), "world": found["world"], "class": found["class"], "kind": found["kind"], "id": fid, "filename": target.name}
        self._append_unique(self.state.pending_pictures, item, key=lambda x: (x["id"], x["filename"], x["source"]))

    def _auto_match_image(self, target):
        candidate_id = self._candidate_id_from_image_name(target.name)
        if not candidate_id:
            return None
        ok, reason = is_safe_filename_component(candidate_id)
        if not ok:
            self.state.warnings.append(f"图片文件名推断出的候选 ID 非法，已跳过自动绑定：{target.name} -> {candidate_id}（{reason}）"); return None
        found = self._find_by_indexes(candidate_id)
        if not found:
            return None
        return {"source": str(target), "filename": target.name, "id": candidate_id, "world": found["world"], "class": found["class"], "kind": found["kind"]}

    def _load_image(self):
        self.state.clear(); self._new_session(); self.state.mode = "image"
        files = self._recursive_image_files()
        base = self.source_data / "image_inputs"
        if not files:
            print("未在 source_data/image_inputs 及其子目录中发现图片文件。"); return
        self.print_section("load-image")
        print("可用图片文件：")
        for i, p in enumerate(files, 1):
            rel = p.relative_to(base) if self._policy("progress_policy", "show_relative_path", True) else p.name
            print(f"  {i}. {rel}")
        print("  all. 全部加载")
        choice = input("请输入要导入的图片序号，或输入 all: ").strip().lower()
        if choice == "all":
            matched, unmatched = [], []
            total = len(files)
            for i, target in enumerate(files, 1):
                rel = target.relative_to(base) if self._policy("progress_policy", "show_relative_path", True) else target.name
                self.print_progress(i, total, f"正在分析图片: {rel}")
                m = self._auto_match_image(target)
                (matched if m else unmatched).append(m or target)
            accept_all = False
            if matched:
                print("检测到可自动匹配的图片：")
                for i, m in enumerate(matched, 1):
                    print(f"{i}. {m['filename']} -> {m['id']}")
                    print(f"   World: {m['world']}")
                    print(f"   Class: {m['class']}")
                    print(f"   Kind: {m['kind'] or '-'}")
                print("\n你可以输入：yes / no / all / none")
                for m in matched:
                    if accept_all:
                        self._append_unique(self.state.pending_pictures, m, key=lambda x: (x["id"], x["filename"], x["source"]))
                        continue
                    ans = input(f"是否绑定 {m['filename']} -> {m['id']} ? (yes/no/all/none): ").strip().lower()
                    if ans == "all":
                        accept_all = True
                        self._append_unique(self.state.pending_pictures, m, key=lambda x: (x["id"], x["filename"], x["source"]))
                    elif ans == "yes":
                        self._append_unique(self.state.pending_pictures, m, key=lambda x: (x["id"], x["filename"], x["source"]))
                    elif ans == "none":
                        break
                    else:
                        self.state.warnings.append(f"自动匹配图片已跳过：{m['filename']}")
            if self._policy("image_binding_policy", "fallback_to_manual_when_unmatched", True):
                for i, target in enumerate(unmatched, 1):
                    self.print_progress(i, len(unmatched), f"正在手动绑定图片: {target.name}")
                    self._load_single_image_manual(target)
            self._write_report("precheck_report.md", self._build_precheck_report("已处理全部图片文件"))
            print(f"已处理全部图片文件，共 {len(files)} 个。可执行 preview / report / commit。")
            self.print_section("load-image done"); return
        try:
            target = files[int(choice)-1]
        except Exception:
            print("输入无效。"); return
        self.print_progress(1,1, f"正在分析图片: {target.relative_to(base)}")
        matched = self._auto_match_image(target)
        if matched:
            print("检测到可自动匹配的图片：")
            print(f"{matched['filename']} -> {matched['id']}")
            print(f"  World: {matched['world']}")
            print(f"  Class: {matched['class']}")
            print(f"  Kind: {matched['kind'] or '-'}")
            if input("是否绑定该关系？(yes/no): ").strip().lower() == "yes":
                self._append_unique(self.state.pending_pictures, matched, key=lambda x: (x["id"], x["filename"], x["source"]))
            elif self._policy("image_binding_policy", "fallback_to_manual_when_unmatched", True):
                self._load_single_image_manual(target)
        else:
            self._load_single_image_manual(target)
        self._write_report("precheck_report.md", self._build_precheck_report(f"已载入图片：{target.relative_to(base)}"))
        print("图片已加入待提交列表。可执行 preview / commit。")
        self.print_section("load-image done")

    def _load_single_package(self, target):
        split_dir = target / "Data_Spilt"
        if split_dir.exists():
            for p in split_dir.rglob("*.json"):
                if p.name == "INDEX.json":
                    continue
                rel = p.relative_to(split_dir)
                parts = rel.parts
                if len(parts) < 3:
                    self.state.blocking.append(f"包内 Split 路径层级错误：{p}"); continue
                world, class_name = parts[0], parts[1]
                kind = parts[2] if self._is_special_class(class_name) and len(parts) >= 4 else None
                try:
                    data = read_json(p)
                except Exception as e:
                    self.state.blocking.append(f"包内 JSON 解析失败：{p.name} -> {e}"); continue
                fid = normalize_text(get_field(data, "ID", "id")) or p.stem
                ok, reason = is_safe_filename_component(fid)
                if not ok:
                    self._apply_severity(self._policy("conflict_policy", "invalid_id", "blocking"), f"包内非法 ID：{fid}（{reason}，来源 {p.name}）"); continue
                item = {"id": fid, "world": world, "class": class_name, "kind": kind, "data": data, "source": str(p)}
                self._append_unique(self.state.pending_split, item, key=lambda x: x["id"])
        pic_dir = target / "Picture"
        if pic_dir.exists():
            for p in pic_dir.rglob("*"):
                if not p.is_file():
                    continue
                rel = p.relative_to(pic_dir)
                parts = rel.parts
                if len(parts) < 4:
                    self.state.blocking.append(f"包内图片路径层级错误：{p}"); continue
                world, class_name = parts[0], parts[1]
                if self._is_special_class(class_name):
                    if len(parts) < 5:
                        self.state.blocking.append(f"特殊类图片路径层级错误：{p}"); continue
                    kind, fid = parts[2], parts[3]
                else:
                    kind, fid = None, parts[2]
                ok, reason = is_safe_filename_component(str(fid))
                if not ok:
                    self.state.blocking.append(f"包内图片目标 ID 非法：{fid}（{reason}，来源 {p.name}）"); continue
                item = {"source": str(p), "world": world, "class": class_name, "kind": kind, "id": fid, "filename": p.name}
                self._append_unique(self.state.pending_pictures, item, key=lambda x: (x["id"], x["filename"], x["source"]))
        delete_json = target / "Delete.json"
        if delete_json.exists():
            try:
                items = list(read_json(delete_json).get("items", []))
                for fid in items:
                    fid = str(fid)
                    ok, reason = is_safe_filename_component(fid)
                    if not ok:
                        self.state.blocking.append(f"Delete.json 中非法 ID：{fid}（{reason}）"); continue
                    self._append_unique(self.state.pending_delete, fid)
            except Exception:
                self.state.blocking.append(f"Delete.json 解析失败：{target.name}")

    def _load_package(self):
        self.state.clear(); self._new_session(); self.state.mode = "package"
        packages = self._recursive_package_dirs()
        base = self.source_data / "relay_packages"
        if not packages:
            print("未在 source_data/relay_packages 及其子目录中发现候选包目录。"); return
        self.print_section("load-package")
        print("可用包目录：")
        for i, p in enumerate(packages, 1):
            rel = p.relative_to(base) if self._policy("progress_policy", "show_relative_path", True) else p.name
            print(f"  {i}. {rel}")
        print("  all. 全部加载")
        choice = input("请输入要读取的包序号，或输入 all: ").strip().lower()
        if choice == "all":
            total = len(packages)
            for i, target in enumerate(packages, 1):
                rel = target.relative_to(base) if self._policy("progress_policy", "show_relative_path", True) else target.name
                self.print_progress(i, total, f"正在读取包目录: {rel}")
                self._load_single_package(target)
            self._write_report("precheck_report.md", self._build_precheck_report("已读取全部包目录"))
            print(f"已读取全部包目录，共 {len(packages)} 个。可执行 preview / report / commit。")
            self.print_section("load-package done"); return
        try:
            target = packages[int(choice)-1]
        except Exception:
            print("输入无效。"); return
        self.print_progress(1,1, f"正在读取包目录: {target.relative_to(base)}")
        self._load_single_package(target)
        self._write_report("precheck_report.md", self._build_precheck_report(f"已读取包：{target.relative_to(base)}"))
        print(f"已读取包：{target.relative_to(base)}。可执行 preview / report / commit。")
        self.print_section("load-package done")

    def do_preview(self, arg):
        self.print_section("preview")
        split_groups = {}
        for x in self.state.pending_split:
            world_dir = self.resolve_world_dir_name(x.get("world"))
            key = f"{world_dir}/{x.get('class','?')}/{x.get('kind') or '-'}"
            split_groups[key] = split_groups.get(key, 0) + 1
        text = ["# 变更摘要","",f"时间：{now_iso()}",f"模式：{self.state.mode or '-'}","",
                "## 源数据层待提交",f"- Split：{len(self.state.pending_split)}",f"- 图片：{len(self.state.pending_pictures)}",f"- 删除：{len(self.state.pending_delete)}","",
                "## Split 分组统计"]
        if split_groups:
            for k,v in sorted(split_groups.items()):
                text.append(f"- {k}: {v}")
        else:
            text.append("- 无")
        text += ["","## Merge 层待提交",f"- Merge 重建目标：{len(self.state.pending_merge)}"]
        report = "\n".join(text)
        path = self._write_report("preview_report.md", report)
        print(report)
        print(f"\n已输出摘要报告：{path}")
        self.print_section("preview done")

    def do_report(self, arg):
        self.print_section("report")
        if not self.state.last_report or not self.state.last_report.exists():
            print("当前没有可用报告。")
            self.print_section("report done")
            return
        print(f"最近一次报告：{self.state.last_report}")
        print("-"*60)
        print(self.state.last_report.read_text(encoding="utf-8"))
        self.print_section("report done")

    def _commit_source(self):
        changed_split_dirs, changed_picture_dirs = set(), set()
        changed_split_worlds, changed_picture_worlds = set(), set()
        self.print_section("commit source")
        total_split = len(self.state.pending_split)
        for i,item in enumerate(self.state.pending_split,1):
            self.print_progress(i, total_split, f"正在写入 Split: {item['id']}")
            leaf = self._split_leaf_dir(item["world"], item["class"], item.get("kind"))
            ensure_dir(leaf)
            write_json(leaf / f"{item['id']}.json", item["data"])
            changed_split_dirs.add(leaf)
            changed_split_worlds.add(self.resolve_world_dir_name(item["world"]))
        total_pic = len(self.state.pending_pictures)
        for i,item in enumerate(self.state.pending_pictures,1):
            self.print_progress(i, total_pic, f"正在写入图片: {item['filename']} -> {item['id']}")
            if item.get("world") is None:
                found = self._find_feature_by_id(item["id"])
                if not found:
                    self.state.blocking.append(f"图片目标不存在，无法提交：{item['id']}"); continue
                item["world"], item["class"], item["kind"] = found["world"], found["class"], found["kind"]
            leaf = self._picture_leaf_dir(item["world"], item["class"], item.get("kind"))
            id_dir = leaf / item["id"]
            ensure_dir(id_dir)
            existing_nums = []
            for f in id_dir.iterdir():
                if f.is_file() and f.stem.startswith(item["id"] + "_"):
                    try: existing_nums.append(int(f.stem.split("_")[-1]))
                    except Exception: pass
            next_n = max(existing_nums) + 1 if existing_nums else 1
            ext = Path(item["filename"]).suffix or Path(item["source"]).suffix or ".jpg"
            shutil.copy2(item["source"], id_dir / f"{item['id']}_{next_n}{ext}")
            changed_picture_dirs.add(leaf)
            changed_picture_worlds.add(self.resolve_world_dir_name(item["world"]))
        total_del = len(self.state.pending_delete)
        for i,fid in enumerate(self.state.pending_delete,1):
            self.print_progress(i, total_del, f"正在处理删除: {fid}")
            found = self._find_feature_by_id(fid)
            if not found:
                self.state.warnings.append(f"删除目标不存在：{fid}"); continue
            try:
                found["path"].unlink(missing_ok=True)
                changed_split_dirs.add(self._split_leaf_dir(found["world"], found["class"], found.get("kind")))
                changed_split_worlds.add(str(found["world"]))
            except Exception as e:
                self.state.warnings.append(f"删除 JSON 失败：{fid} -> {e}")
            pdir = self._picture_leaf_dir(found["world"], found["class"], found.get("kind")) / fid
            if pdir.exists():
                shutil.rmtree(pdir, ignore_errors=True)
                changed_picture_dirs.add(self._picture_leaf_dir(found["world"], found["class"], found.get("kind")))
                changed_picture_worlds.add(str(found["world"]))
        for d in changed_split_dirs: self._rebuild_split_index(d)
        for d in changed_picture_dirs: self._rebuild_picture_index(d)
        if changed_split_dirs:
            self._bump_root_index(self.split_root)
            for world_dir_name in sorted(changed_split_worlds):
                self._bump_world_index(self.split_root, world_dir_name)
        if changed_picture_dirs:
            self._bump_root_index(self.picture_root)
            for world_dir_name in sorted(changed_picture_worlds):
                self._bump_world_index(self.picture_root, world_dir_name)
        self.print_section("commit source done")
        return changed_split_dirs, changed_picture_dirs

    def _queue_rebuild_target(self, world, class_name, kind):
        item = {"world": world, "class": class_name, "kind": kind}
        self._append_unique(self.state.pending_merge, item, key=lambda x: (str(x["world"]), x["class"], x.get("kind")))

    def _resolve_rebuild_targets(self, arg):
        if arg.strip() == "--all":
            if not self.split_root.exists():
                return
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
            total = len(targets)
            for i,(world,class_name,kind) in enumerate(targets,1):
                self.print_progress(i, total, f"正在登记重建目标: {world} / {class_name} / {kind or '-'}")
                self._queue_rebuild_target(world, class_name, kind)
            return
        parts = arg.split()
        if len(parts) == 2:
            self._queue_rebuild_target(parts[0], parts[1], None)
        elif len(parts) == 3:
            self._queue_rebuild_target(parts[0], parts[1], parts[2])
        else:
            self.state.blocking.append(f"rebuild 参数不合法：{arg}")

    def _commit_merge(self):
        chunk_size = int(self.tool_config.get("chunk_size", 200))
        changed_dirs = set()
        changed_worlds = set()
        self.print_section("commit merge")
        total_targets = len(self.state.pending_merge)
        for ti,target in enumerate(self.state.pending_merge,1):
            world_dir = self.resolve_world_dir_name(target["world"])
            self.print_progress(ti, total_targets, f"正在重建 Merge: {world_dir} / {target['class']} / {target.get('kind') or '-'}")
            leaf = self._split_leaf_dir(target["world"], target["class"], target.get("kind"))
            mleaf = self._merge_leaf_dir(target["world"], target["class"], target.get("kind"))
            ensure_dir(mleaf)
            for p in mleaf.glob("chunk_*.json"): p.unlink(missing_ok=True)
            items = []
            if leaf.exists():
                source_files = sorted([p for p in leaf.glob("*.json") if p.name != "INDEX.json"])
                for si,p in enumerate(source_files,1):
                    if self._policy("progress_policy", "show_chunk_progress", True):
                        self.print_progress(si, len(source_files), f"正在读取要素: {p.name}")
                    try:
                        obj = read_json(p)
                        if isinstance(obj, dict): items.append(obj)
                    except Exception:
                        self.state.warnings.append(f"重建时跳过非法 JSON：{p}")
            total_chunks = max(1, (len(items) + chunk_size - 1) // chunk_size)
            for i in range(0, len(items), chunk_size):
                fname = f"chunk_{(i // chunk_size) + 1:03d}.json"
                if self._policy("progress_policy", "show_chunk_progress", True):
                    self.print_progress((i // chunk_size) + 1, total_chunks, f"正在输出 chunk: {fname}")
                write_json(mleaf / fname, items[i:i+chunk_size])
            self._rebuild_merge_index(mleaf, chunk_size)
            changed_dirs.add(mleaf)
            changed_worlds.add(world_dir)
        if changed_dirs:
            self._bump_root_index(self.merge_root)
            for world_dir_name in sorted(changed_worlds):
                self._bump_world_index(self.merge_root, world_dir_name)
        self.print_section("commit merge done")
        return changed_dirs

    def do_commit(self, arg):
        if self.state.blocking:
            print("当前存在阻断问题，不能提交。请先执行 report 查看详情。"); return
        if not any([self.state.pending_split, self.state.pending_pictures, self.state.pending_delete, self.state.pending_merge]):
            print("当前没有待提交内容。"); return
        source_pending = any([self.state.pending_split, self.state.pending_pictures, self.state.pending_delete])
        merge_pending = bool(self.state.pending_merge)
        scope = []
        if source_pending: scope.append("源数据层")
        if merge_pending: scope.append("Merge 层")
        if input(f"这将把当前 staged 的{' + '.join(scope)}结果写入正式仓库。是否继续？(yes/no): ").strip().lower() != "yes":
            print("已取消提交。"); return
        changed_split_dirs = changed_picture_dirs = changed_merge_dirs = set()
        if source_pending: changed_split_dirs, changed_picture_dirs = self._commit_source()
        if merge_pending: changed_merge_dirs = self._commit_merge()
        report_text = "\n".join([
            "# 提交报告","",f"时间：{now_iso()}",
            f"提交范围：{' + '.join(scope)}",
            f"- Split：{len(self.state.pending_split)}",
            f"- 图片：{len(self.state.pending_pictures)}",
            f"- 删除：{len(self.state.pending_delete)}",
            f"- Merge：{len(self.state.pending_merge)}",
            f"- 受影响 Split 目录：{len(changed_split_dirs)}",
            f"- 受影响 Picture 目录：{len(changed_picture_dirs)}",
            f"- 受影响 Merge 目录：{len(changed_merge_dirs)}","",
            "说明：本版本已执行真实写库，并支持图片自动绑定、World 映射、冲突详情与进度提示。"
        ])
        path = self._write_report("commit_report.md", report_text)
        print(f"提交完成。报告已输出：{path}")
        self.state.clear()

    def do_rebuild(self, arg):
        if not arg:
            print("用法示例：")
            print("  rebuild zth RLE")
            print("  rebuild zth ISG station")
            print("  rebuild --all"); return
        if not self.state.session_dir: self._new_session()
        self.state.mode = "rebuild"
        self.print_section("rebuild")
        self._resolve_rebuild_targets(arg.strip())
        self._write_report("precheck_report.md", self._build_precheck_report(f"已登记 rebuild 目标：{arg.strip()}"))
        print(f"已登记待重建目标：{arg.strip()}。当前会在 commit 时真正写入 Data_Merge。")
        self.print_section("rebuild done")

    def do_sync_web_schema(self, arg):
        self.print_section("sync-web-schema")
        source_file = self.web_schema_source / "featureFormats.ts"
        if not source_file.exists():
            print("未找到 web_schema/source/featureFormats.ts，无法同步。")
            self.print_section("sync-web-schema done"); return
        text = source_file.read_text(encoding="utf-8")
        pairs = re.findall(r"(\\w+)\\s*:\\s*(\\d+)", text)
        if pairs:
            data = {"_comment": "由 featureFormats.ts 自动解析生成。可手动检查，但建议重新同步。"}
            for world_id, code in pairs:
                data[str(code)] = world_id
            write_json(self.world_map_path, data)
            self.world_map = {k: v for k, v in data.items() if not k.startswith("_")}
            print(f"已解析 world_map，共 {len(self.world_map)} 项。")
        classes = re.findall(r'"(ISG|ISL|ISP)"', text)
        if classes:
            data = {"_comment": "由 featureFormats.ts 自动解析生成。当前这些 Class 需要再按 Kind 分层。", "special_classes": sorted(set(classes))}
            write_json(self.special_class_rules_path, data)
            self.special_class_set = set(data["special_classes"])
            print(f"已解析特殊类规则，共 {len(self.special_class_set)} 项。")
        print("同步完成。")
        self.print_section("sync-web-schema done")

    def do_discard(self, arg):
        old = self.state.session_dir.name if self.state.session_dir else "-"
        self.state.clear()
        print(f"当前暂存内容已丢弃。原 session：{old}")

    def do_clear(self, arg):
        self.state.mode = None
        print("当前命令上下文已清空。")

    def do_help(self, arg):
        print("可用命令：")
        print("  help             显示帮助")
        print("  status           显示当前会话状态")
        print("  load-package     读取标准 RelayPackage")
        print("  load-json        读取单独 JSON 输入")
        print("  load-image       读取单独图片输入")
        print("  preview          输出当前待提交摘要")
        print("  report           查看最近一次报告")
        print("  commit           提交当前暂存变更")
        print("  rebuild          重建指定范围的 Data_Merge")
        print("  discard          丢弃当前暂存结果")
        print("  clear            清空当前命令上下文")
        print("  sync-web-schema  同步并解析 web_schema/source/featureFormats.ts")
        print("  exit             退出工具")
        print("")
        print("增强点：")
        print("  - load-package / load-json / load-image 均支持 all")
        print("  - 递归扫描子目录")
        print("  - load-image 会尝试根据 *_n 文件名自动匹配要素 ID")
        print("  - World code 会通过 web_schema/cache/world_map.json 解析为仓库目录名")
        print("  - 冲突等级、递归扫描、进度提示等均可从 config/policy_config.json 调整")

    def do_status(self, arg):
        print("当前会话状态：")
        print(f"  模式: {self.state.mode or '-'}")
        print(f"  待写入 Split 数量: {len(self.state.pending_split)}")
        print(f"  待写入图片数量: {len(self.state.pending_pictures)}")
        print(f"  待删除数量: {len(self.state.pending_delete)}")
        print(f"  待重建 Merge 数量: {len(self.state.pending_merge)}")
        print(f"  警告数量: {len(self.state.warnings)}")
        print(f"  阻断问题数量: {len(self.state.blocking)}")
        if self.state.mode == "json":
            print(f"  JSON 总对象数: {self.state.stats['json_total_objects']}")
            print(f"  JSON 识别成功数: {self.state.stats['json_recognized_objects']}")
            print(f"  JSON 跳过数: {self.state.stats['json_skipped_objects']}")
            print(f"  JSON 重复 ID 数: {self.state.stats['json_duplicate_ids']}")
        print(f"  当前 session: {self.state.session_dir.name if self.state.session_dir else '-'}")
        print(f"  当前 World 映射数量: {len(self.world_map)}")
        print(f"  当前特殊类数量: {len(self.special_class_set)}")

    def do_exit(self, arg):
        print("正在退出工具。")
        return True

    def default(self, line):
        cmd_name = line.strip()
        if cmd_name == "load-package":
            return self._load_package()
        if cmd_name == "load-json":
            return self._load_json()
        if cmd_name == "load-image":
            return self._load_image()
        if cmd_name == "sync-web-schema":
            return self.do_sync_web_schema("")
        print(f"未知命令：{cmd_name}")
        print("可用命令：")
        print("  " + ", ".join(VALID_COMMANDS))


if __name__ == "__main__":
    ToolShell().cmdloop()
