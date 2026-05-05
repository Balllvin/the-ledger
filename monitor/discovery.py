from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .sanitize import sanitize
from .utils import file_info, path_for_display
from .opencode import opencode_roots


TEXT_EXTENSIONS = {".env", ".ini", ".json", ".md", ".py", ".toml", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml"}
SKIP_PARTS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
CODEX_MARKERS = ("CODEX_HOME", ".codex", "codex_auth", "codex", "state_5.sqlite", "logs_2.sqlite")


def discover_local_sources(home: Path | None = None) -> dict[str, Any]:
    base = home or Path.home()
    scan_roots = _scan_roots(base)
    codex_roots = _discover_codex_roots(base, scan_roots)
    codex_app_roots = _discover_codex_app_roots(base)
    hermes_roots = _discover_hermes_roots(base, scan_roots)
    opencode_roots_found = _discover_opencode_roots(base, scan_roots)
    app_roots = _discover_codex_linked_apps(scan_roots)
    return sanitize(
        {
            "scanRoots": [path_for_display(path) for path in scan_roots],
            "codexRoots": codex_roots,
            "codexAppRoots": codex_app_roots,
            "hermesRoots": hermes_roots,
            "opencodeRoots": opencode_roots_found,
            "appRoots": app_roots,
        }
    )


def preferred_codex_root(discovery: dict[str, Any], home: Path | None = None) -> Path:
    env_root = os.environ.get("CODEX_HOME")
    if env_root:
        return Path(env_root).expanduser()
    roots = discovery.get("codexRoots") or []
    for item in roots:
        if item.get("exists"):
            return Path(str(item["path"])).expanduser()
    return (home or Path.home()) / ".codex"


def preferred_lattice_root(discovery: dict[str, Any], home: Path | None = None) -> Path:
    env_root = os.environ.get("AI_USAGE_MONITOR_LATTICE_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    for item in discovery.get("appRoots") or []:
        if item.get("hasLatticeDb"):
            return Path(str(item["path"])).expanduser()
    return (home or Path.home()) / "Desktop" / "Lattice"


def _scan_roots(home: Path) -> list[Path]:
    env_roots = _env_paths("AI_USAGE_MONITOR_SCAN_ROOTS")
    if env_roots:
        return _existing_unique(env_roots)
    names = ("Desktop", "Documents", "Downloads", "Developer", "dev", "code", "projects", "source")
    candidates = [home / name for name in names]
    candidates.extend(_env_paths("AI_USAGE_MONITOR_EXTRA_APP_ROOTS"))
    return _existing_unique(candidates)


def _discover_codex_roots(home: Path, scan_roots: Iterable[Path]) -> list[dict[str, Any]]:
    candidates = [home / ".codex", *_env_paths("CODEX_HOME")]
    for root in scan_roots:
        candidates.extend(_find_named_dirs(root, ".codex", max_depth=4, limit=40))
    roots = []
    seen: set[str] = set()
    for path in candidates:
        resolved = _safe_resolve(path)
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(
            {
                **file_info(resolved),
                "stateDb": file_info(resolved / "state_5.sqlite"),
                "logsDb": file_info(resolved / "logs_2.sqlite"),
                "auth": {**file_info(resolved / "auth.json"), "redacted": True},
            }
        )
    roots.sort(key=lambda item: (not bool(item.get("exists")), str(item.get("path"))))
    return roots


def _discover_codex_app_roots(home: Path) -> list[dict[str, Any]]:
    candidates = [
        home / "Library" / "Application Support" / "Codex",
        home / "AppData" / "Roaming" / "Codex",
        home / ".config" / "Codex",
        home / ".local" / "share" / "Codex",
    ]
    roots = []
    seen: set[str] = set()
    for path in candidates:
        resolved = _safe_resolve(path)
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(
            {
                **file_info(resolved),
                "preferences": file_info(resolved / "Preferences"),
                "browserSidebarLocalServers": file_info(resolved / "browser-sidebar-local-servers.json"),
            }
        )
    roots.sort(key=lambda item: (not bool(item.get("exists")), str(item.get("path"))))
    return roots


def _discover_hermes_roots(home: Path, scan_roots: Iterable[Path]) -> list[dict[str, Any]]:
    candidates = [
        home / ".hermes",
        home / ".local" / "state" / "hermes",
        home / "Desktop" / "brain spa" / "brain-spa" / "runtime" / "hermes" / "chipmunk",
        home / "Desktop" / "brain-spa" / "runtime" / "hermes" / "chipmunk",
        *_env_paths("AI_USAGE_MONITOR_HERMES_ROOTS"),
    ]
    for root in scan_roots:
        if _safe_resolve(root) == _safe_resolve(home):
            continue
        candidates.extend(_find_hermes_state_dirs(root, max_depth=7, limit=20))
    roots = []
    seen: set[str] = set()
    for path in candidates:
        resolved = _safe_resolve(path)
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(
            {
                **file_info(resolved),
                "auth": {**file_info(resolved / "auth.json"), "redacted": True},
                "stateDb": file_info(resolved / "state.db"),
                "sessions": file_info(resolved / "sessions"),
                "gatewayState": file_info(resolved / "gateway_state.json"),
            }
        )
    roots.sort(key=lambda item: (not bool(item.get("exists")), str(item.get("path"))))
    return roots


def _discover_opencode_roots(home: Path, scan_roots: Iterable[Path]) -> list[dict[str, Any]]:
    candidates = list(opencode_roots(home).values())
    for root in scan_roots:
        candidates.extend(_find_named_dirs(root, ".opencode", max_depth=4, limit=20))
        candidates.extend(_find_git_opencode_dirs(root, max_depth=6, limit=20))
    roots = []
    seen: set[str] = set()
    for path in candidates:
        resolved = _safe_resolve(path)
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(
            {
                **file_info(resolved),
                "auth": {**file_info(resolved / "auth.json"), "redacted": True},
                "database": file_info(resolved / "opencode.db"),
                "logs": file_info(resolved / "log"),
            }
        )
    roots.sort(key=lambda item: (not bool(item.get("exists")), str(item.get("path"))))
    return roots


def _discover_codex_linked_apps(scan_roots: Iterable[Path]) -> list[dict[str, Any]]:
    signals: dict[Path, Counter[str]] = defaultdict(Counter)
    latest: dict[Path, float] = defaultdict(float)
    for root in scan_roots:
        for path in _iter_files(root, max_depth=5, limit=8000):
            marker = _file_marker(path)
            if not marker:
                continue
            app_root = _app_root_for(path, root)
            signals[app_root][marker] += 1
            try:
                latest[app_root] = max(latest[app_root], path.stat().st_mtime)
            except OSError:
                pass

    apps = []
    for root, counts in signals.items():
        apps.append(
            {
                "path": path_for_display(root),
                "signals": dict(counts.most_common()),
                "signalCount": sum(counts.values()),
                "hasLatticeDb": (root / "data" / "lattice.db").exists(),
                "latestSignal": latest.get(root),
            }
        )
    apps.sort(key=lambda item: (int(item.get("signalCount") or 0), float(item.get("latestSignal") or 0)), reverse=True)
    return apps[:30]


def _file_marker(path: Path) -> str | None:
    name = path.name.lower()
    if name in {"state_5.sqlite", "logs_2.sqlite"}:
        return name
    if name == "auth.json" and path.parent.name == ".codex":
        return ".codex/auth.json"
    if "codex_auth" in name:
        return "codex_auth"
    if path.name == "lattice.db":
        return "lattice.db"
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None
    if os.environ.get("AI_USAGE_MONITOR_DEEP_TEXT_SCAN") != "1":
        return None
    try:
        if path.stat().st_size > 262_144:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lowered = text.lower()
    for marker in CODEX_MARKERS:
        if marker.lower() in lowered:
            return marker
    return None


def _app_root_for(path: Path, scan_root: Path) -> Path:
    if path.parent.name == ".codex":
        return path.parent
    try:
        relative = path.relative_to(scan_root)
    except ValueError:
        return path.parent
    if len(relative.parts) <= 2:
        return path.parent if path.name.lower() != "lattice.db" else path.parent.parent
    return scan_root / relative.parts[0]


def _find_named_dirs(root: Path, name: str, *, max_depth: int, limit: int) -> list[Path]:
    found: list[Path] = []
    visited = 0
    for current, dirs, _ in os.walk(root):
        visited += 1
        if visited > 2500:
            break
        current_path = Path(current)
        dirs[:] = [item for item in dirs if item not in SKIP_PARTS]
        if _depth_from(root, current_path) > max_depth:
            dirs[:] = []
            continue
        if current_path.name == name:
            found.append(current_path)
            dirs[:] = []
            if len(found) >= limit:
                break
    return found


def _find_hermes_state_dirs(root: Path, *, max_depth: int, limit: int) -> list[Path]:
    found: list[Path] = []
    visited = 0
    for current, dirs, files in os.walk(root):
        visited += 1
        if visited > 4000:
            break
        current_path = Path(current)
        dirs[:] = [item for item in dirs if item not in SKIP_PARTS and item != "oss-inspection"]
        if _depth_from(root, current_path) > max_depth:
            dirs[:] = []
            continue
        names = set(files)
        if {"state.db", "auth.json", "gateway_state.json"} & names and ("sessions" in dirs or "state.db" in names):
            found.append(current_path)
            dirs[:] = []
            if len(found) >= limit:
                break
    return found


def _find_git_opencode_dirs(root: Path, *, max_depth: int, limit: int) -> list[Path]:
    found: list[Path] = []
    visited = 0
    for current, dirs, _ in os.walk(root):
        visited += 1
        if visited > 2500:
            break
        current_path = Path(current)
        dirs[:] = [item for item in dirs if item not in SKIP_PARTS]
        if _depth_from(root, current_path) > max_depth:
            dirs[:] = []
            continue
        candidate = current_path / ".git" / "opencode"
        if candidate.exists():
            found.append(candidate)
            if len(found) >= limit:
                break
    return found


def _iter_files(root: Path, *, max_depth: int, limit: int) -> Iterable[Path]:
    count = 0
    visited = 0
    for current, dirs, files in os.walk(root):
        visited += 1
        if visited > 2500:
            return
        current_path = Path(current)
        dirs[:] = [item for item in dirs if item not in SKIP_PARTS and item not in {"runtime", "oss-inspection"}]
        if _depth_from(root, current_path) > max_depth:
            dirs[:] = []
            continue
        for file_name in files:
            count += 1
            if count > limit:
                return
            yield current_path / file_name


def _depth_from(root: Path, path: Path) -> int:
    try:
        return len(path.relative_to(root).parts)
    except ValueError:
        return 0


def _env_paths(name: str) -> list[Path]:
    raw = os.environ.get(name, "")
    if not raw:
        return []
    return [Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip()]


def _existing_unique(paths: Iterable[Path]) -> list[Path]:
    result = []
    seen: set[str] = set()
    for path in paths:
        resolved = _safe_resolve(path)
        key = str(resolved).lower()
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        result.append(resolved)
    return result


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()
