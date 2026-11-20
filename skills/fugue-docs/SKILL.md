---
name: fugue-docs
description: >-
  Maintain PROJECT_INDEX.md / FOLDER_INDEX.md / L3 file-header indexes for GEB fractal documentation.
  Use when the user requests Fugue indexes, mentions 赋格, GEB, PROJECT_INDEX, or FOLDER_INDEX,
  asks to initialize or audit documentation isomorphism, or when a Fugue Stop hook asks to fill semantic fields.
---

# 赋格文档 (Antigravity Plugin)

L1 `PROJECT_INDEX.md` 是项目入口，L2 `FOLDER_INDEX.md` 是模块清单，L3 是代码文件头的 `[INPUT]`、`[OUTPUT]`、`[POS]`、`[PROTOCOL]`。依赖、清单行、一致性检查由程序维护；模型只写语义：`[POS]`、`[OUTPUT]` 的含义、清单职责和模块定位。

`<plugin-root>` 是本技能目录的上两级目录（即包含 `plugin.json` 与 `scripts/` 的插件根目录），`<root>` 是当前项目根目录。

## 定位

先读适用的项目规则（`GEMINI.md` / `AGENTS.md`），再读 L1 `PROJECT_INDEX.md`、目标目录 L2 `FOLDER_INDEX.md` 和相关文件头，然后读代码。索引用来缩小范围，不能替代阅读要改的实现。只读审查不初始化文档，不扩大用户的编辑范围；未采用协议的项目仅在用户要求接入时初始化。

## 维护

- **已启用 `fugue-docs-agy` 插件原生钩子**：改完代码无需为日常维护运行同步、检查或计量脚本。每轮结束时，`Stop` 钩子自动处理本会话归属的未提交改动，补新文件 L3 头骨架并同步依赖与清单。出现语义缺口时会收到以“赋格:”开头的续跑提示，按提示每项补一句即可；提示以外的内容不要顺带改写。项目本身的测试仍按任务需要运行。
- **未启用钩子或需要手动回环**：按 [manual-workflow.md](../../references/manual-workflow.md) 手动同步与检查。执行 `--changed` 前先 `--dry-run` 预览范围，避免覆盖他人编辑。
- **Antigravity 边界与排障**：详见 [antigravity.md](../../references/antigravity.md) 与 [ANTIGRAVITY.md](../../adapters/ANTIGRAVITY.md)。

## 初始化（项目还没有索引）

1. 生成架构事实与候选（Windows 使用 `python`，macOS/Linux 使用 `python3`）：
   `python "<plugin-root>/scripts/geb_arch.py" "<root>"`
   未解析项需核对，分数是启发式权重，不是正确概率。
2. 预览并生成骨架：
   `python "<plugin-root>/scripts/geb_scaffold.py" "<root>" --dry-run`
   确认范围后去掉 `--dry-run` 执行。大型存量项目分模块迁移，如实报告覆盖范围。
3. 真读代码后自底向上补齐 L3、L2、L1 的语义占位（`TODO(语义)`）。小项目（≤20 文件）用 L1 + L3。生成代码、依赖、构建产物和纯配置不加 L3。
4. 验证同构性：
   `python "<plugin-root>/scripts/geb_check.py" "<root>" --strict --complete --report`
   模板与协议细节见 [templates.md](../../references/templates.md)、[PROTOCOL.md](../../adapters/PROTOCOL.md)。

## 接入项目级规则或 Git/CI 硬约束

如需把协议写入目标项目的 `GEMINI.md` 或安装自包含的 Git `pre-commit` / CI 检查：
```bash
python "<plugin-root>/scripts/geb_adapt.py" "<root>" --tool antigravity --pre-commit --dry-run
```

## 计量

Antigravity 钩子数据默认保存在 `~/.gemini/fugue/`（可通过 `FUGUE_DATA_DIR` 覆盖）。Antigravity 未公开 token usage 遥测，账本中 `usage` 保持 `null`、`status` 为 `telemetry_unavailable`，不记成零，也不阻塞开发。口径说明见 [token-accounting.md](../../references/token-accounting.md)。
