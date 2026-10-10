## Devin execution conventions

When native Devin hooks are installed and confirmed loaded with CLI `/hooks`, follow Fugue prompts only; do not repeat manual sync, check, or metering scripts. Hooks maintain only projects that have adopted the protocol.

Find tools in this order: `scripts/` in the loaded skill, project `.agents/skills/fugue-docs/scripts/`, project `.devin/skills/fugue-docs/scripts/`, project `scripts/geb/`, then `~/.config/devin/skills/fugue-docs/scripts/`. Confirm `geb_sync.py` and `geb_check.py` exist and use their directory as `<tools-dir>`.

Without confirmed hooks, use the manual loop:
1. Inspect workspace changes, then read L1 → target L2 → file headers and relevant implementation.
2. After editing, preview `python3 "<tools-dir>/geb_sync.py" "<root>" --changed --dry-run`; verify scope before syncing. If changes are mixed with others', maintain only this task's files manually.
3. Complete semantic fields and run `python3 "<tools-dir>/geb_check.py" "<root>" --strict --complete --report` plus relevant tests.

Devin hooks expose no public transcript or usage data, so ledger usage remains unknown; do not use Codex or Claude metering. Files written by backgrounded exec after PostToolUse may not be attributed to this session.
