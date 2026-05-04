from __future__ import annotations

import json
import subprocess
from typing import Any

from .sanitize import sanitize, safe_preview


HERMES_WSL_COLLECTOR = r"""
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

SECRET_KEYS = ("TOKEN", "SECRET", "PASSWORD", "KEY", "AUTH", "COOKIE")

def safe_file(path):
    data = {"path": str(path), "exists": path.exists()}
    if path.exists():
        stat = path.stat()
        data.update({"bytes": stat.st_size, "modified": stat.st_mtime, "is_dir": path.is_dir()})
    return data

def safe_kv_file(path):
    if not path.exists():
        return {"exists": False, "keys": []}
    keys = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        keys.append({"key": key, "present": True, "redacted": any(part in key.upper() for part in SECRET_KEYS)})
    return {"exists": True, "keys": keys}

def safe_json_keys(path):
    if not path.exists():
        return {"exists": False, "keys": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"exists": True, "error": str(exc), "keys": []}
    if isinstance(data, dict):
        return {"exists": True, "keys": sorted(map(str, data.keys()))[:80]}
    if isinstance(data, list):
        return {"exists": True, "type": "list", "items": len(data)}
    return {"exists": True, "type": type(data).__name__}

home = Path.home()
root = home / ".hermes"
agent = root / "hermes-agent"
files = []
by_suffix = Counter()
total_bytes = 0
skip = {".git", "node_modules", "__pycache__"}
if root.exists():
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip for part in path.parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((stat.st_mtime, str(path), stat.st_size, path.suffix.lower() or "[none]"))
        by_suffix[path.suffix.lower() or "[none]"] += 1
        total_bytes += stat.st_size
files.sort(reverse=True)

cron_root = root / "cron" / "output"
cron_files = []
if cron_root.exists():
    for path in cron_root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            cron_files.append({"path": str(path), "bytes": stat.st_size, "modified": stat.st_mtime})
cron_files.sort(key=lambda item: item["modified"], reverse=True)

git = {"available": False}
if (agent / ".git").exists():
    try:
        branch = subprocess.run(["git", "-C", str(agent), "branch", "--show-current"], text=True, capture_output=True, timeout=5)
        head = subprocess.run(["git", "-C", str(agent), "rev-parse", "--short", "HEAD"], text=True, capture_output=True, timeout=5)
        git = {"available": True, "branch": branch.stdout.strip(), "head": head.stdout.strip()}
    except Exception as exc:
        git = {"available": True, "error": str(exc)}

print(json.dumps({
    "home": str(home),
    "root": safe_file(root),
    "agent": safe_file(agent),
    "config": safe_file(root / "config.yaml"),
    "env": safe_kv_file(root / ".env"),
    "channelDirectory": safe_json_keys(root / "channel_directory.json"),
    "gatewayState": safe_json_keys(root / "gateway_state.json"),
    "codexAuth": {**safe_file(home / ".codex" / "auth.json"), "redacted": True},
    "files": len(files),
    "bytes": total_bytes,
    "bySuffix": dict(by_suffix.most_common(30)),
    "latest": [{"path": p, "bytes": b, "modified": m, "suffix": s} for m, p, b, s in files[:40]],
    "cronOutput": {"files": len(cron_files), "latest": cron_files[:25]},
    "git": git,
}, ensure_ascii=False))
"""


def collect_hermes() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["wsl", "python3", "-c", HERMES_WSL_COLLECTOR],
            text=True,
            capture_output=True,
            timeout=15,
        )
    except FileNotFoundError:
        return {"available": False, "error": "wsl command not found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "error": "Hermes WSL scan timed out"}

    if completed.returncode != 0:
        return {
            "available": False,
            "error": safe_preview(completed.stderr or completed.stdout or f"wsl exited {completed.returncode}"),
        }
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"available": False, "error": f"Unable to parse Hermes WSL scan: {safe_preview(exc)}"}
    data["available"] = True
    return sanitize(data)
