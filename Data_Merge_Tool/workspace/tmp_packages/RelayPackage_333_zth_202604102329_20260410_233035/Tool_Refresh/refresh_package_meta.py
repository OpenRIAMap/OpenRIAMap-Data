from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

def now_iso():
    return datetime.now(TZ).replace(microsecond=0).isoformat()

def count_json_features(root: Path) -> int:
    data_root = root / "Data_Spilt"
    if not data_root.exists():
        return 0
    return sum(1 for p in data_root.rglob("*.json") if p.name.lower() != "index.json")

def count_pictures(root: Path) -> int:
    pic_root = root / "Picture"
    if not pic_root.exists():
        return 0
    return sum(1 for p in pic_root.rglob("*") if p.is_file())

def count_deletes(root: Path) -> int:
    p = root / "Delete.json"
    if not p.exists():
        return 0
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    items = obj.get("items") if isinstance(obj, dict) else []
    return len(items) if isinstance(items, list) else 0

def main():
    root = Path(__file__).resolve().parent.parent
    index_path = root / "INDEX.json"
    try:
        index_obj = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    except Exception:
        index_obj = {}
    if not isinstance(index_obj, dict):
        index_obj = {}
    index_obj["featureCount"] = count_json_features(root)
    index_obj["pictureCount"] = count_pictures(root)
    index_obj["deleteCount"] = count_deletes(root)
    if "exportedAt" in index_obj:
        index_obj["exportedAt"] = now_iso()
    else:
        index_obj["updatedAt"] = now_iso()
    index_path.write_text(json.dumps(index_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("INDEX.json refreshed")

if __name__ == "__main__":
    main()