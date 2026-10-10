---
name: fugue-docs
description: Maintain PROJECT_INDEX.md / FOLDER_INDEX.md / file-header indexes for coding agents. Use when the user requests Fugue indexes or mentions 赋格, GEB, PROJECT_INDEX, or FOLDER_INDEX. With enabled and trusted Fugue hooks in Codex, Devin, or Claude Code, routine maintenance runs automatically; use this skill for initialization, semantic gaps requested by a hook, or index questions. Without those hooks, also use when editing code in adopted projects to manually sync and check the task's changes. Missing telemetry never blocks development.
---

# 赋格文档

L1 `PROJECT_INDEX.md` 是项目入口,L2 `FOLDER_INDEX.md` 是模块清单,L3 是代码文件头的 `[INPUT]`、`[OUTPUT]`、`[POS]`、`[PROTOCOL]`。依赖、清单行、一致性检查和计量由程序维护;模型只写语义:`[POS]`、`[OUTPUT]` 的含义、清单职责和模块定位。`<skill-dir>` 是本文件所在目录,`<root>` 是项目根目录。

## 定位

先读适用的项目规则,再读 L1、目标目录 L2 和相关文件头,然后读代码。索引用来缩小范围,不能替代阅读要改的实现。只读审查不初始化文档,不扩大用户的编辑范围;未采用协议的项目仅在用户要求接入时初始化。

## 维护

- **Codex / Devin + 已启用并信任的原生钩子 / Claude Code + 插件钩子**:改完代码无需为日常维护运行同步、检查或计量脚本。每轮结束时,钩子只处理本会话归属的未提交改动,补新文件头部骨架、同步依赖与清单、记录可用遥测。出现语义缺口时会收到以“赋格:”开头的提示并继续执行,按提示每项补一句;提示以外的内容不要顺带改写。项目本身的测试仍按任务需要运行。
- **未启用或未信任钩子**:按 [references/manual-workflow.md](references/manual-workflow.md) 手动同步、检查。`--changed` 包含整个仓库的未提交改动,先预览范围,保留用户和其他代理的编辑。不要仅因技能文件存在就假定钩子已启用。
- **Codex 接入**:使用 `$fugue-docs` 显式初始化或咨询;`geb_install_codex.py --hooks` 安装原生钩子,由 Codex 自身完成信任审查。安装、环境要求见 [references/codex.md](references/codex.md),事件与维护边界见 [references/codex-hooks.md](references/codex-hooks.md)。未采用协议的项目不自动初始化。
- **Devin 接入**:`geb_install_devin.py --hooks` 显式安装原生钩子;用 CLI `/hooks` 确认已加载。未确认时按 [references/manual-workflow.md](references/manual-workflow.md) 手动维护。Devin 没有公开用量数据,账本保持未知;宿主限制见 [references/devin.md](references/devin.md)。

## 初始化(项目还没有索引)

1. `python3 "<skill-dir>/scripts/geb_arch.py" "<root>"` 生成架构事实与候选;未解析项需要核对,分数是启发式权重,不是正确概率。
2. `python3 "<skill-dir>/scripts/geb_scaffold.py" "<root>" --dry-run` 查看范围,再去掉 `--dry-run` 生成骨架。大型存量项目分模块迁移,如实报告覆盖范围。
3. 读代码后自底向上补齐 L3、L2、L1 的语义占位。小项目用 L1 + L3。生成代码、依赖、构建产物和纯配置不加 L3。
4. `python3 "<skill-dir>/scripts/geb_check.py" "<root>" --strict --complete --report` 验证。模板与协议细节见 [references/templates.md](references/templates.md)、[adapters/PROTOCOL.md](adapters/PROTOCOL.md)。

## 计量

已启用的 Codex 原生钩子自动记录当前会话的本地遥测,默认账本为 `${CODEX_HOME:-~/.codex}/fugue/metrics`,`FUGUE_DATA_DIR` 可改数据目录。无钩子时手动计量仍为可选,仅在用户要求且日志可读、账本可写时运行。缺少遥测或会话身份不符时用量为 unknown/未知,静默继续,不反复 `doctor`、不为计量提权。没有可比对照时节省量也为未知。Claude Code 钩子账本默认在 `~/.claude/fugue/metrics`。口径与汇总命令见 [references/token-accounting.md](references/token-accounting.md)。
