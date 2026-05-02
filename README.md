# keep-codex-fast

Codex desktop maintenance as a CLI, Codex skill, automation template, and script.

It audits local Codex sessions, archived sessions, worktrees, config, state databases, logs, skills, plugins, memories, and automations. Cleanup is conservative: it backs up first, refuses mutation while Codex is running, never kills processes, and skips git worktree moves unless explicitly requested.

## Install

```bash
npm i -g keep-codex-fast
keep-codex-fast setup
```

Then run audits or cleanup:

```bash
keep-codex-fast audit
keep-codex-fast apply
```

For manual cleanup, quit Codex first, then run:

```bash
keep-codex-fast apply --days 10 --worktree-days 14 --log-max-mb 250
```

## Install the Skill with Skills CLI

After this repo is public on GitHub:

```bash
npx skills add k0nkupa/keep-codex-fast --skill keep-codex-fast -g -y --copy
```

The skill lives at:

```text
skills/keep-codex-fast/SKILL.md
```

## Homebrew

During development:

```bash
brew install --HEAD ./Formula/keep-codex-fast.rb
```

For a public tap, publish a GitHub release, update the formula URL/SHA, then users can run:

```bash
brew tap k0nkupa/keep-codex-fast
brew install keep-codex-fast
keep-codex-fast setup
```

## Commands

```bash
keep-codex-fast setup   # install skill and weekly automation into ~/.codex
keep-codex-fast audit   # run report-only maintenance
keep-codex-fast apply   # run cleanup; script refuses while Codex is open
keep-codex-fast doctor  # show install/runtime checks
```

## Development

```bash
npm test
npm run check
npm run pack:dry
```
