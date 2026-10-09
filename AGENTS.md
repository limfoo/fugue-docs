# Codex repository guide

This repository provides the fugue-docs skill and deterministic GEB documentation tools. Use Python 3.9+ and the standard library; there is no dependency installation step. Read `PROJECT_INDEX.md`, then the relevant `scripts/FOLDER_INDEX.md` or `evals/FOLDER_INDEX.md` and implementation before editing.

## Changes

- Keep the shared GEB protocol in `adapters/PROTOCOL.md` and its English/compact counterparts consistent. Codex-specific execution guidance belongs in `adapters/CODEX.md` and `adapters/CODEX_EN.md`; skill guidance lives in `SKILL.md` and `references/`.
- `scripts/geb_install_codex.py` installs a standalone skill; explicit `--hooks` also merges native Codex hook configuration. Keep `.claude-plugin/` and Claude hook registration out of that package. Preserve both Claude Code and Codex workflows, and never bypass Codex's hook trust review.
- Preserve unrelated working-tree changes. `geb_sync.py --changed` covers all dirty files, including other agents' work: inspect its dry run before writing. Update L3 headers, affected L2 entries, and L1 when structure changes. New source files need all four L3 tags.
- Keep installation paths portable and quoted. Do not hard-code a developer's home directory, change global Codex/Git configuration, or install hooks as a side effect of ordinary development.
- Enabled Codex hooks handle synchronization and metering automatically; without hooks, use the manual workflow and optional metering. Missing local telemetry in cloud/sandbox sessions means unknown usage, and does not block maintenance or semantic feedback.
- Hook protocol changes must match actual Codex payloads and output semantics. `apply_patch` and canonical `Bash` events share the existing maintenance engine; Codex and Claude session state and token accounting remain distinct. Test Stop continuation and loop suppression without calling a real model.

## Validation

Use focused unittest modules while developing. Before finishing changes to tooling, run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B evals/run_regression_suite.py --rounds 1
```

This runs integration tests, unittest discovery, and the repository's strict/complete index checks. For documentation-only edits, run `python3 -B scripts/geb_check.py . --strict --complete --report`. Keep generated test output in `/tmp`, not in committed results unless publishing new measurement evidence is requested.

`evals/run_token_pilot.py` and `evals/run-first-round.sh --execute` launch real models. Ordinary regression work uses offline tests; run a live pilot only when it is part of the user's task.
