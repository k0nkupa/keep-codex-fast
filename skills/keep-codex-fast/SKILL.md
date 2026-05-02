---
name: keep-codex-fast
description: Run Codex desktop maintenance to keep local sessions, worktrees, logs, config, and state from slowing the app down. Use when the user asks to keep Codex fast, clean/archive old Codex chats, prune Codex config projects, rotate Codex logs, archive stale Codex worktrees, or create a repeatable Codex maintenance report.
metadata:
  short-description: Maintain local Codex state, sessions, logs, and worktrees
---

# Keep Codex Fast

Use this skill for local Codex desktop maintenance. Default to evidence-first audit mode; only mutate local Codex state when the user explicitly asks for cleanup/apply.

## Core Rule

If Codex is running, inspect only. Do not mutate sessions, the state database, logs, worktrees, or config while the app may also be touching them.

## Fast Path

Run the installed script:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/keep-codex-fast/scripts/codex_fast_maintenance.py"
```

For cleanup after Codex is closed:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/keep-codex-fast/scripts/codex_fast_maintenance.py" --apply
```

Useful options:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/keep-codex-fast/scripts/codex_fast_maintenance.py" --days 10 --worktree-days 14 --log-max-mb 250
python3 "${CODEX_HOME:-$HOME/.codex}/skills/keep-codex-fast/scripts/codex_fast_maintenance.py" --report /tmp/codex-fast-report.md
python3 "${CODEX_HOME:-$HOME/.codex}/skills/keep-codex-fast/scripts/codex_fast_maintenance.py" --apply --archive-git-worktrees
keep-codex-fast audit
keep-codex-fast apply
```

## Maintenance Contract

1. Inspect space usage for sessions, archived sessions, worktrees, archived worktrees, logs, config, plugins, skills, memories, automations, and local state databases.
2. Back up important files before changing anything: config, state databases, log databases, memories, skills, plugins, automations, and any session files that will move.
3. Check whether Codex is open. If it is, report only.
4. Identify giant active chats from the `threads` table and rollout file sizes.
5. Archive old non-current active chats older than 7-10 days by moving rollout files to archived sessions and updating `threads.archived`.
6. Keep only recent execution threads active.
7. Recommend handoff docs for old high-token threads before archiving when the content is still operationally important.
8. Normalize obvious Windows extended path prefixes in config when present.
9. Prune dead project entries only when the path no longer exists and the entry is clearly temporary or generated.
10. Report stale Codex worktrees. Move only non-git stale folders by default; moving git worktrees requires explicit `--archive-git-worktrees`.
11. Rotate oversized Codex log databases into an archive folder so Codex can recreate fresh logs.
12. Report heavy Node/dev-server/background processes; do not auto-kill them.
13. Verify after cleanup: config parses, database opens, integrity check passes, active session count/size dropped, archived count increased, and bad paths are gone.
14. Prefer weekly maintenance over one-time rescue cleanup.
15. Keep the final report boring: what changed, what was skipped, what still needs manual attention.

## Safety Notes

- Never delete session files, worktrees, logs, memories, skills, plugins, or automations as part of this skill. Move or back up only.
- Treat pinned/current status conservatively. If pin metadata is unavailable, skip recent threads and surface older high-token candidates for handoff review.
- Do not auto-move git worktrees unless the user explicitly accepts that this can break git worktree metadata in exchange for freeing hot-folder space.
- Do not kill background processes. List them with PID, command, and rough memory where available.
- Do not claim cleanup happened unless the script ran with `--apply` and reported changes.
