from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MACOS_DATALESS_FLAG = 0x40000000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def timestamp_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = str(value)
        return text if text else None
    if number > 10_000_000_000:
        number = number / 1000
    try:
        return datetime.fromtimestamp(number, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return None


def path_for_display(path: Path | str) -> str:
    text = str(path)
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return text


def file_info(path: Path) -> dict[str, Any]:
    exists = path.exists()
    info: dict[str, Any] = {
        "path": path_for_display(path),
        "exists": exists,
    }
    if exists:
        stat = path.stat()
        info.update(
            {
                "bytes": stat.st_size,
                "modified": timestamp_to_iso(stat.st_mtime),
                "is_dir": path.is_dir(),
            }
        )
    return info


def count_files(root: Path, *, patterns: Iterable[str] = ("*",), skip_parts: set[str] | None = None, max_files: int = 10000) -> dict[str, Any]:
    if not root.exists():
        return {"path": path_for_display(root), "exists": False, "files": 0, "bytes": 0}
    skip_parts = skip_parts or set()
    total_files = 0
    total_bytes = 0
    by_suffix: Counter[str] = Counter()
    latest: list[tuple[float, Path, int]] = []
    for pattern in patterns:
        for item in root.rglob(pattern):
            if total_files >= max_files:
                break
            if not item.is_file():
                continue
            if skip_parts and any(part in skip_parts for part in item.parts):
                continue
            if is_dataless(item):
                continue
            try:
                stat = item.stat()
            except OSError:
                continue
            total_files += 1
            total_bytes += stat.st_size
            by_suffix[item.suffix.lower() or "[none]"] += 1
            latest.append((stat.st_mtime, item, stat.st_size))
    latest.sort(reverse=True)
    return {
        "path": path_for_display(root),
        "exists": True,
        "files": total_files,
        "bytes": total_bytes,
        "truncated": total_files >= max_files,
        "bySuffix": dict(by_suffix.most_common(20)),
        "latest": [
            {
                "path": path_for_display(path),
                "bytes": size,
                "modified": timestamp_to_iso(mtime),
            }
            for mtime, path, size in latest[:25]
        ],
    }


def open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=1.0)
    con.execute("pragma query_only = on")
    con.execute("pragma busy_timeout = 1000")
    con.row_factory = sqlite3.Row
    return con


def query_rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def table_count(con: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(con.execute(f"select count(*) from [{table}]").fetchone()[0])
    except sqlite3.Error:
        return None


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path_for_display(path)


def default_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def desktop_root(home: Path | None = None) -> Path:
    base = home or default_home()
    return base / "Desktop"


def is_dataless(path: Path) -> bool:
    try:
        flags = getattr(path.stat(), "st_flags", 0)
    except OSError:
        return False
    return bool(flags & MACOS_DATALESS_FLAG)
