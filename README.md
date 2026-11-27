# Fugue Docs for Codex

在 Linux VPS 上安装赋格文档技能和九个 Codex 生命周期钩子。这个分发分支名为 `codex-plugin`，插件版本为 `0.1.0`。原项目及其他宿主的接入方式见 [main 分支](https://github.com/limfoo/fugue-docs/tree/main)。

## 在 VPS 安装

使用运行 Codex 的同一个 Linux 账户。需要 Git、Python 3.9 或以上版本，以及提供 `codex plugin marketplace` 命令的 Codex CLI。插件只使用 Python 标准库。

```sh
codex plugin marketplace add limfoo/fugue-docs --ref codex-plugin
codex plugin add fugue-docs@fugue-local
codex plugin list --marketplace fugue-local
```

在 VPS 上启动新的 Codex 会话，输入 `/hooks`，审阅并信任来源为 `fugue-docs@fugue-local` 的九个钩子。已安装独立版 Fugue 的账户，应先核对用户级和项目级钩子，避免同一事件执行两次。

## 在项目中使用

进入项目根目录并启动 Codex。第一次采用 Fugue 时，在对话中输入：

```text
$fugue-docs:fugue-docs 为当前项目初始化赋格索引。
```

已有索引的项目可以直接使用。钩子从本会话的文件改动中识别需要同步的索引，并在收尾时提示补写职责说明。[插件索引](plugins/fugue-docs/PROJECT_INDEX.md) · [事件说明](plugins/fugue-docs/skills/fugue-docs/references/codex-hooks.md)
