#!/usr/bin/env python3
"""Audit and safely maintain local Codex desktop state."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sqlite3
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ThreadRow:
    id: str
    rollout_path: Path
    updated_at: int
    title: str
    tokens_used: int
    cwd: str
    archived: int


def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{n} B"


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {".Trash"}]
        for name in files:
            p = Path(root) / name
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def file_count(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for p in path.rglob(pattern) if p.is_file())


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def is_safe_session_file(codex_home: Path, path: Path) -> bool:
    return path.suffix == ".jsonl" and (
        is_under(path, codex_home / "sessions") or is_under(path, codex_home / "archived_sessions")
    )


def codex_processes() -> list[str]:
    try:
        out = subprocess.check_output(["ps", "-axo", "pid=,comm=,args="], text=True)
    except Exception:
        return []
    matches: list[str] = []
    own_pid = os.getpid()
    for line in out.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text = stripped.split(maxsplit=1)[0]
        try:
            if int(pid_text) == own_pid:
                continue
        except ValueError:
            pass
        lowered = stripped.lower()
        if (
            "/Applications/Codex.app/" in stripped
            or re.search(r"(^|\s)Codex($|\s)", stripped)
            or re.search(r"(^|\s)codex\s+app-server($|\s)", lowered)
        ):
            if "codex_fast_maintenance.py" not in stripped:
                matches.append(stripped)
    return matches


def find_state_db(codex_home: Path) -> Path | None:
    candidates = sorted(codex_home.glob("state*.sqlite"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return candidates[0] if candidates else None


def open_threads(db_path: Path) -> list[ThreadRow]:
    if not db_path or not db_path.exists():
        return []
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            """
            SELECT id, rollout_path, updated_at, title, tokens_used, cwd, archived
            FROM threads
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [
        ThreadRow(
            id=row[0],
            rollout_path=Path(row[1]),
            updated_at=int(row[2] or 0),
            title=row[3] or "",
            tokens_used=int(row[4] or 0),
            cwd=row[5] or "",
            archived=int(row[6] or 0),
        )
        for row in rows
    ]


def backup_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)


def backup_important(codex_home: Path, backup_root: Path, session_files: Iterable[Path]) -> None:
    backup_root.mkdir(parents=True, exist_ok=True)
    for name in ["config.toml", "memories", "skills", "plugins", "automations"]:
        backup_tree(codex_home / name, backup_root / name)
    for path in codex_home.glob("state*.sqlite"):
        backup_tree(path, backup_root / "databases" / path.name)
    for path in codex_home.glob("logs*.sqlite"):
        backup_tree(path, backup_root / "databases" / path.name)
    backup_tree(codex_home / "sqlite", backup_root / "sqlite")
    for path in session_files:
        if path.exists() and is_safe_session_file(codex_home, path):
            backup_tree(path, backup_root / "session-files" / path.name)


def sqlite_integrity(db_path: Path | None) -> str:
    if not db_path or not db_path.exists():
        return "missing"
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            return str(conn.execute("PRAGMA integrity_check;").fetchone()[0])
    except Exception as exc:
        return f"error: {exc}"


def config_status(config_path: Path) -> tuple[str, list[str], list[str]]:
    if not config_path.exists():
        return "missing", [], []
    text = config_path.read_text(errors="replace")
    bad_windows_paths = re.findall(r"\\\\\?\\[A-Za-z]:\\[^\"'\n]+", text)
    dead_projects: list[str] = []
    try:
        parsed = tomllib.loads(text)
        projects = parsed.get("projects", {})
        if isinstance(projects, dict):
            for path in projects:
                if isinstance(path, str) and path.startswith("/") and not Path(path).exists():
                    dead_projects.append(path)
        return "ok", bad_windows_paths, dead_projects
    except Exception as exc:
        return f"parse error: {exc}", bad_windows_paths, dead_projects


def prune_config(config_path: Path) -> tuple[int, int]:
    text = config_path.read_text()
    normalized = re.sub(r"\\\\\?\\([A-Za-z]:\\)", r"\1", text)
    status, _bad, dead_projects = config_status(config_path)
    if not status.startswith("ok"):
        return 0, 0
    prunable = [
        p
        for p in dead_projects
        if p.startswith("/private/var/")
        or p.startswith("/var/folders/")
        or p.startswith(str(Path.home() / "Documents" / "Codex"))
        or p.startswith(str(Path.home() / ".symphony" / "workspaces"))
    ]
    removed = 0
    for project_path in prunable:
        escaped = re.escape(project_path)
        pattern = re.compile(rf'\n\[projects\."{escaped}"\]\n(?:[^\n].*\n?)*?(?=\n\[projects\.|\Z)', re.MULTILINE)
        normalized, count = pattern.subn("\n", normalized)
        removed += count
    if normalized != text:
        tomllib.loads(normalized)
        tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
        tmp_path.write_text(normalized)
        tmp_path.replace(config_path)
    return len(prunable), removed


def top_active_threads(threads: list[ThreadRow], limit: int = 15) -> list[tuple[ThreadRow, int]]:
    active = [t for t in threads if t.archived == 0]
    active.sort(key=lambda t: (t.tokens_used, t.rollout_path.stat().st_size if t.rollout_path.exists() else 0), reverse=True)
    return [(t, t.rollout_path.stat().st_size if t.rollout_path.exists() else 0) for t in active[:limit]]


def stale_threads(codex_home: Path, threads: list[ThreadRow], days: int, max_count: int) -> list[ThreadRow]:
    cutoff = int((dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).timestamp())
    selected = [
        t
        for t in threads
        if t.archived == 0
        and t.updated_at < cutoff
        and t.rollout_path.exists()
        and is_safe_session_file(codex_home, t.rollout_path)
        and "[pinned]" not in t.title.lower()
        and "pinned:" not in t.title.lower()
    ]
    selected.sort(key=lambda t: t.updated_at)
    return selected[:max_count]


def archive_threads(codex_home: Path, db_path: Path, threads: list[ThreadRow]) -> int:
    archive_dir = codex_home / "archived_sessions"
    archive_dir.mkdir(parents=True, exist_ok=True)
    now = int(dt.datetime.now(dt.UTC).timestamp())
    moved = 0
    copied: list[tuple[Path, Path, str]] = []
    for thread in threads:
        src = thread.rollout_path
        if not src.exists() or not is_safe_session_file(codex_home, src):
            continue
        dest = archive_dir / src.name
        if dest.exists():
            dest = archive_dir / f"{src.stem}-{thread.id}{src.suffix}"
        tmp_dest = dest.with_suffix(dest.suffix + ".tmp")
        shutil.copy2(src, tmp_dest)
        tmp_dest.replace(dest)
        copied.append((src, dest, thread.id))
    with sqlite3.connect(db_path) as conn:
        for src, dest, thread_id in copied:
            conn.execute(
                "UPDATE threads SET archived = 1, archived_at = ?, rollout_path = ? WHERE id = ?",
                (now, str(dest), thread_id),
            )
            moved += 1
        conn.commit()
    for src, _dest, _thread_id in copied:
        try:
            src.unlink()
        except FileNotFoundError:
            pass
    return moved


def contains_git_metadata(path: Path) -> bool:
    if (path / ".git").exists():
        return True
    return any(p.exists() for p in path.rglob(".git"))


def git_dirty(path: Path) -> bool:
    git_dirs = []
    if (path / ".git").exists():
        git_dirs.append(path)
    for p in path.rglob(".git"):
        if p.exists():
            git_dirs.append(p.parent)
    for repo in git_dirs:
        try:
            out = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL)
            if out.strip():
                return True
        except Exception:
            return True
    return False


def stale_worktrees(codex_home: Path, days: int) -> list[Path]:
    root = codex_home / "worktrees"
    if not root.exists():
        return []
    cutoff = dt.datetime.now().timestamp() - days * 86400
    candidates = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                candidates.append(path)
        except OSError:
            pass
    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates


def archive_worktrees(codex_home: Path, candidates: list[Path], archive_stamp: str, include_git_worktrees: bool) -> tuple[int, list[str]]:
    dest_root = codex_home / "archived_worktrees" / archive_stamp
    dest_root.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped: list[str] = []
    for path in candidates:
        if not is_under(path, codex_home / "worktrees"):
            skipped.append(f"{path} (outside Codex worktrees root)")
            continue
        if contains_git_metadata(path) and not include_git_worktrees:
            skipped.append(f"{path} (git worktree; skipped unless --archive-git-worktrees is set)")
            continue
        if git_dirty(path):
            skipped.append(f"{path} (dirty or unreadable git status)")
            continue
        dest = dest_root / path.name
        if dest.exists():
            dest = dest_root / f"{path.name}-{moved + 1}"
        shutil.move(str(path), str(dest))
        moved += 1
    return moved, skipped


def rotate_logs(codex_home: Path, max_mb: int, archive_stamp: str) -> int:
    moved = 0
    dest_root = codex_home / "maintenance_archive" / archive_stamp / "logs"
    for path in codex_home.glob("logs*.sqlite"):
        try:
            if path.stat().st_size <= max_mb * 1024 * 1024:
                continue
        except OSError:
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest_root / path.name))
        moved += 1
    return moved


def heavy_processes(limit: int = 15) -> list[str]:
    try:
        out = subprocess.check_output(["ps", "-axo", "pid=,rss=,command="], text=True)
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        pid, rss, command = parts
        if re.search(r"\b(node|bun|vite|next|webpack|ts-node|tsx|npm|yarn|pnpm)\b", command):
            try:
                rows.append((int(rss), pid, command))
            except ValueError:
                pass
    rows.sort(reverse=True)
    return [f"{pid} {human_size(rss * 1024)} {command[:180]}" for rss, pid, command in rows[:limit]]


def write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and safely maintain local Codex desktop state.")
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--apply", action="store_true", help="Apply safe cleanup. Refuses mutation while Codex is running.")
    parser.add_argument("--days", type=int, default=10, help="Archive active sessions older than this many days.")
    parser.add_argument("--worktree-days", type=int, default=14, help="Archive clean worktree folders older than this many days.")
    parser.add_argument("--log-max-mb", type=int, default=250, help="Rotate logs_*.sqlite files larger than this size.")
    parser.add_argument("--max-sessions", type=int, default=200, help="Maximum stale sessions to archive in one run.")
    parser.add_argument("--archive-git-worktrees", action="store_true", help="Also move clean stale git worktrees. Default is report-only to avoid breaking git worktree metadata.")
    parser.add_argument("--report", default="", help="Markdown report path.")
    args = parser.parse_args()

    codex_home = Path(args.codex_home).expanduser()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = Path(args.report).expanduser() if args.report else codex_home / "maintenance_reports" / f"codex-fast-{stamp}.md"
    state_db = find_state_db(codex_home)
    threads = open_threads(state_db) if state_db else []
    active_threads = [t for t in threads if t.archived == 0]
    archived_threads = [t for t in threads if t.archived == 1]
    processes = codex_processes()
    can_apply = args.apply and not processes

    stale = stale_threads(codex_home, threads, args.days, args.max_sessions)
    worktree_candidates = stale_worktrees(codex_home, args.worktree_days)
    config_parse, bad_windows_paths, dead_projects = config_status(codex_home / "config.toml")
    before_active_size = sum(t.rollout_path.stat().st_size for t in active_threads if t.rollout_path.exists())
    before_archived_count = len(archived_threads)

    changes: list[str] = []
    skipped: list[str] = []
    backup_root = codex_home / "maintenance_backups" / stamp

    if args.apply and processes:
        skipped.append("Apply requested but Codex appears to be running; inspection only.")

    if can_apply:
        backup_important(codex_home, backup_root, [t.rollout_path for t in stale])
        changes.append(f"Backup created: {backup_root}")
        if stale and state_db:
            moved = archive_threads(codex_home, state_db, stale)
            changes.append(f"Archived active session files: {moved}")
        prunable, removed = prune_config(codex_home / "config.toml")
        changes.append(f"Pruned config project candidates: {removed}/{prunable}")
        moved_worktrees, dirty_skips = archive_worktrees(codex_home, worktree_candidates, stamp, args.archive_git_worktrees)
        changes.append(f"Archived clean stale worktrees: {moved_worktrees}")
        skipped.extend(dirty_skips)
        moved_logs = rotate_logs(codex_home, args.log_max_mb, stamp)
        changes.append(f"Rotated oversized log databases: {moved_logs}")
        threads = open_threads(state_db) if state_db else []
        active_threads = [t for t in threads if t.archived == 0]
        archived_threads = [t for t in threads if t.archived == 1]
        config_parse, bad_windows_paths, dead_projects = config_status(codex_home / "config.toml")

    after_active_size = sum(t.rollout_path.stat().st_size for t in active_threads if t.rollout_path.exists())

    lines = [
        "# Codex Fast Maintenance Report",
        "",
        f"- Mode: {'apply' if can_apply else 'audit'}",
        f"- Codex home: `{codex_home}`",
        f"- Report: `{report_path}`",
        f"- Codex running: {'yes' if processes else 'no'}",
        f"- Config parse: {config_parse}",
        f"- State DB integrity: {sqlite_integrity(state_db)}",
        "",
        "## Space",
    ]
    for label, path in [
        ("sessions", codex_home / "sessions"),
        ("archived_sessions", codex_home / "archived_sessions"),
        ("worktrees", codex_home / "worktrees"),
        ("archived_worktrees", codex_home / "archived_worktrees"),
        ("plugins", codex_home / "plugins"),
        ("skills", codex_home / "skills"),
        ("memories", codex_home / "memories"),
        ("automations", codex_home / "automations"),
        ("state_db", state_db or codex_home / "state.sqlite"),
        ("logs_db", codex_home / "logs_2.sqlite"),
    ]:
        lines.append(f"- {label}: {human_size(dir_size(path))} ({file_count(path)} files)")

    lines.extend(
        [
            "",
            "## Sessions",
            f"- Active threads: {len(active_threads)}",
            f"- Archived threads: {len(archived_threads)}",
            f"- Active rollout file size: {human_size(after_active_size)}",
            f"- Active rollout file size before apply: {human_size(before_active_size)}",
            f"- Archived thread count before apply: {before_archived_count}",
            f"- Stale active sessions older than {args.days} days: {len(stale)}",
            "",
            "## Biggest Active Threads",
        ]
    )
    for thread, size in top_active_threads(threads):
        updated = dt.datetime.fromtimestamp(thread.updated_at, dt.UTC).strftime("%Y-%m-%d")
        title = thread.title.replace("\n", " ")[:100]
        lines.append(f"- {human_size(size)} / {thread.tokens_used:,} tokens / {updated} / `{thread.id}` / {title}")

    lines.extend(["", "## Config"])
    lines.append(f"- Bad Windows extended paths: {len(bad_windows_paths)}")
    for path in bad_windows_paths[:20]:
        lines.append(f"  - `{path}`")
    lines.append(f"- Dead project paths: {len(dead_projects)}")
    for path in dead_projects[:30]:
        lines.append(f"  - `{path}`")

    lines.extend(["", "## Worktrees"])
    lines.append(f"- Stale worktree folders older than {args.worktree_days} days: {len(worktree_candidates)}")
    for path in worktree_candidates[:30]:
        lines.append(f"  - `{path}`")

    lines.extend(["", "## Background Processes"])
    for proc in heavy_processes():
        lines.append(f"- `{proc}`")
    if not heavy_processes():
        lines.append("- None found.")

    lines.extend(["", "## Changes"])
    if changes:
        lines.extend(f"- {change}" for change in changes)
    else:
        lines.append("- None.")

    lines.extend(["", "## Skipped"])
    if skipped:
        lines.extend(f"- {item}" for item in skipped)
    else:
        lines.append("- None.")

    if processes:
        lines.extend(["", "## Codex Processes"])
        lines.extend(f"- `{p}`" for p in processes[:20])

    write_report(report_path, lines)
    print(f"Report: {report_path}")
    print(f"Mode: {'apply' if can_apply else 'audit'}")
    print(f"Codex running: {'yes' if processes else 'no'}")
    print(f"Active threads: {len(active_threads)}")
    print(f"Archived threads: {len(archived_threads)}")
    print(f"Stale active sessions: {len(stale)}")
    print(f"Stale worktrees: {len(worktree_candidates)}")
    print(f"Config parse: {config_parse}")
    print(f"State DB integrity: {sqlite_integrity(state_db)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
