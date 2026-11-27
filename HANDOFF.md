# 分发维护

这个分支发布经过验证的 Fugue Docs 插件。发布 0.1.0 时，以原有 Codex 技能和事件适配器为基准；项目源码对照版本为 [123d989](https://github.com/limfoo/fugue-docs/tree/123d98985fcb23e4a03c6c76c93fb1b0f046fb41)。

插件使用 `.codex-plugin/plugin.json`。在 CLI 0.166.0 和桌面内置 0.171.0-alpha.13.2 的验证中，额外加入插件根级 `plugin.json` 后，技能仍可发现，但钩子列表变成零项。升级时同时检查技能和钩子的数量。

安装清单的插件路径从市场根目录解析。Linux 钩子通过 `python3` 运行并从 `PLUGIN_ROOT` 定位脚本。路径含空格时，事件命令中的双引号必须保留。
