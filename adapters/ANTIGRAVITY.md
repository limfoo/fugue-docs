## Antigravity 执行约定

当 `fugue-docs-agy` 插件已启用且原生 hooks 正常运行时，改完代码只需遵循收工时的“赋格:”语义补写提示即可，不要重复执行手动同步、检查或计量脚本。钩子只维护已存在 `PROJECT_INDEX.md` 的项目，未采用协议的项目零打扰。

找工具时依次检查：已启用插件目录 `~/.gemini/config/plugins/fugue-docs-agy/scripts/`、项目 `.agents/plugins/fugue-docs-agy/scripts/`、项目 `.agents/skills/fugue-docs/scripts/`、项目 `scripts/geb/`。确认找到 `geb_sync.py` 与 `geb_check.py` 后，将所在目录作为 `<tools-dir>`。

未启用插件 hooks 时，使用手动回环：
1. 先检查工作区改动，读 L1 → 目标 L2 → 文件头和相关实现。
2. 编辑后预览 `python3 "<tools-dir>/geb_sync.py" "<root>" --changed --dry-run`（Windows 下用 `python`）；核对范围后再执行同步，混有他人改动时只手动维护本任务文件。
3. 补全语义字段并运行 `python3 "<tools-dir>/geb_check.py" "<root>" --strict --complete --report` 与相关测试。

Antigravity hooks 未公开 token usage 遥测；账本中的 `usage` 保持未知（`telemetry_unavailable`），后台守护命令（`IsDaemon`）在 `PostToolUse` 之后才写入的文件可能无法归属本会话。
