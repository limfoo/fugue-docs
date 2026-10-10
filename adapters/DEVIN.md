## Devin 执行约定

当 Devin 原生 hooks 已安装并通过 CLI `/hooks` 确认加载时,遵循赋格提示即可;不要重复执行手动同步、检查或计量脚本。钩子只维护已采用协议的项目。

找工具时依次检查:已加载技能的 `scripts/`、项目 `.agents/skills/fugue-docs/scripts/`、项目 `.devin/skills/fugue-docs/scripts/`、项目 `scripts/geb/`、`~/.config/devin/skills/fugue-docs/scripts/`。确认找到 `geb_sync.py` 与 `geb_check.py` 后,将所在目录作为 `<tools-dir>`。

未确认 hooks 已加载时,使用手动回环:
1. 先检查工作区改动,读 L1 → 目标 L2 → 文件头和相关实现。
2. 编辑后预览 `python3 "<tools-dir>/geb_sync.py" "<root>" --changed --dry-run`;核对范围后再执行同步,混有他人改动时只手动维护本任务文件。
3. 补全语义字段并运行 `python3 "<tools-dir>/geb_check.py" "<root>" --strict --complete --report` 与相关测试。

Devin hooks 没有公开会话 transcript/用量;账本中的 usage 保持未知,不执行 Codex 或 Claude 计量流程。后台 exec 在 PostToolUse 之后才写入的文件可能无法归属本会话。
