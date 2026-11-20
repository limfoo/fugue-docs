## Antigravity Execution Conventions

When the `fugue-docs-agy` plugin is enabled with native hooks active, follow the Fugue semantic prompts at turn completion; do not manually re-run sync, check, or metering scripts for routine edits. Hooks only operate on projects that have already adopted `PROJECT_INDEX.md`.

Locate tools in order: `~/.gemini/config/plugins/fugue-docs-agy/scripts/`, `<root>/.agents/plugins/fugue-docs-agy/scripts/`, `<root>/.agents/skills/fugue-docs/scripts/`, or `<root>/scripts/geb/`.

When hooks are disabled, fall back to the manual loop:
1. Read L1 -> target L2 -> file headers and relevant source before editing.
2. Preview `python3 "<tools-dir>/geb_sync.py" "<root>" --changed --dry-run` (use `python` on Windows) and sync only verified task changes.
3. Fill semantic fields and run `python3 "<tools-dir>/geb_check.py" "<root>" --strict --complete --report` plus project tests.

Antigravity hooks do not expose token usage telemetry; `usage` remains unknown (`telemetry_unavailable`). Files written by background daemon commands after `PostToolUse` may not be attributed to the current session.
