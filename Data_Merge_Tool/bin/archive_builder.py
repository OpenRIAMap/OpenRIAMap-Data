from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import shutil
import zipfile


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


def prepare_archive_workspace(workspace_root: Path) -> dict:
    push_id = datetime.now().strftime("push_%Y%m%d_%H%M%S")
    root = workspace_root / "push_tmp" / push_id
    archive_root = root / "archive"
    source_data_root = archive_root / "source_data"
    logs_root = archive_root / "logs"
    ensure_dir(source_data_root)
    ensure_dir(logs_root)
    return {
        "push_id": push_id,
        "root": root,
        "archive_root": archive_root,
        "source_data_root": source_data_root,
        "logs_root": logs_root,
    }


def copy_tree_contents(src: Path, dst: Path) -> dict:
    ensure_dir(dst)
    copied = []
    total_bytes = 0
    if not src.exists():
        return {"file_count": 0, "total_bytes": 0, "copied_paths": []}
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        target = dst / rel
        ensure_dir(target.parent)
        shutil.copy2(path, target)
        copied.append(str(rel))
        total_bytes += path.stat().st_size
    return {"file_count": len(copied), "total_bytes": total_bytes, "copied_paths": copied}


def write_manifest(archive_root: Path, manifest: dict) -> Path:
    path = archive_root / "manifest.json"
    path.write_text(json.dumps(_json_safe(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_zip(archive_root: Path, output_root: Path, base_name: str) -> Path:
    ensure_dir(output_root)
    candidate = output_root / base_name
    stem = candidate.stem
    suffix = candidate.suffix
    idx = 0
    while candidate.exists():
        idx += 1
        candidate = output_root / f"{stem}_{idx}{suffix}"
    with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in archive_root.rglob("*"):
            if path.is_dir():
                continue
            zf.write(path, arcname=path.relative_to(archive_root.parent))
    return candidate
