# 在 Codex 中使用赋格文档

本地市场中的插件名为 `fugue-docs@fugue-local`。安装时需要 Python 3.9+ 和 Git。Windows 使用 PATH 中的 `python`，macOS 与 Linux 使用 `python3`。

在新会话选择赋格文档技能，输入「为当前项目初始化赋格索引」。已接入的项目可以直接使用索引。钩子首次运行前，在桌面设置的 Hooks 或 CLI 的 `/hooks` 中审阅插件来源。个人或项目中已有独立版注册时，请先迁移，避免重复触发。

插件接收九类生命周期事件。[事件说明](codex-hooks.md)列出每个事件的职责。钩子暂不可用时，可以按[手动维护流程](manual-workflow.md)完成当前任务。旧安装器 `geb_install_codex.py` 专供独立安装，插件由 Codex 插件管理器维护。

计量继续使用 `FUGUE_DATA_DIR` 或 Codex 用户目录下的 `fugue`，详见[计量口径](token-accounting.md)。
