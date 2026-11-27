# Fugue Docs · Codex 插件

插件为 Codex 提供项目索引、目录清单和代码文件头维护。代码来自本机 Fugue 安装清单，原作者与协议归属见 [LICENSE](LICENSE)。对照仓库为 [limfoo/fugue-docs](https://github.com/limfoo/fugue-docs/tree/123d98985fcb23e4a03c6c76c93fb1b0f046fb41)。

| 入口 | 用途 |
| --- | --- |
| [.codex-plugin/plugin.json](.codex-plugin/plugin.json) | 插件标识、展示信息与 Codex 组件清单 |
| [hooks/hooks.json](hooks/hooks.json) | 九类 Codex 事件、匹配规则和超时 |
| [skills/fugue-docs/SKILL.md](skills/fugue-docs/SKILL.md) | 初始化、定位和手动维护入口 |
| [scripts/FOLDER_INDEX.md](skills/fugue-docs/scripts/FOLDER_INDEX.md) | 运行时文件清单与职责 |
| [references/codex-hooks.md](skills/fugue-docs/references/codex-hooks.md) | 主会话、子代理、工具和停止事件的行为 |

事件从插件缓存中的脚本进入 `geb_codex_hook.py`，再调用共享维护引擎 `geb_hook.py`。计量沿用现有 Fugue 数据目录。Windows 入口在 Python 中读取 `PLUGIN_ROOT`，适用含空格的路径。
