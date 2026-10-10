# Devin 接入

需要 Python 3.9+。Devin CLI 支持项目与用户级 hooks,也能发现 `.agents/skills/<name>/SKILL.md` 技能。本说明中的 hooks 行为以 Devin CLI 文档为依据;云端会话是否加载仓库 hooks 尚未确认。

## 安装

从 fugue-docs 仓库目录运行:

```bash
python3 scripts/geb_install_devin.py --project /path/to/project --hooks --dry-run
python3 scripts/geb_install_devin.py --project /path/to/project --hooks
```

技能安装到项目 `.agents/skills/fugue-docs/`;显式 `--hooks` 才写入 `.devin/hooks.v1.json`。项目文件的内容本身就是事件对象,不包在 `"hooks"` 键中,命令通过 `$DEVIN_PROJECT_DIR` 定位技能,不绑定安装机器的绝对路径。

用户级安装:

```bash
python3 scripts/geb_install_devin.py --user --hooks --dry-run
python3 scripts/geb_install_devin.py --user --hooks
```

技能目录为 `~/.config/devin/skills/fugue-docs/`,用户 hooks 写入 `~/.config/devin/config.json` 的 `"hooks"` 键,命令使用该技能的绝对路径。`--hooks` 可省略以仅安装技能;`--update` 只更新受管清单内未被修改的文件,`--dry-run` 预检且不写盘。技能复制使用白名单和独立清单,保留其他技能文件;hooks 更新仅替换命令中带 `geb_devin_hook.py` 的条目,保留其他键、事件与 hook。

安装后在 Devin CLI 使用 `/hooks` 确认 hooks 已加载。项目与用户 hooks 会累加,同一项目只应注册一份赋格 hooks。安装器不改 Git 配置、不初始化项目索引、不写入 Claude 插件 hook 注册;`.claude-plugin/` 安装只提供技能,不会配置 Devin hooks。

## 事件与职责

| Devin 事件 | 注册范围 | 赋格行为 |
|---|---|---|
| `SessionStart` | 全部会话 | 仅对已采用协议的项目保存会话状态并注入索引导航 |
| `UserPromptSubmit` | 全部提示 | 清理被外部继续修改文件的归属记录 |
| `PreToolUse` | `edit`、`write`、`notebook_edit`、`apply_patch`、`exec` | 跟踪文件目标、解析补丁结构行,或记录 exec 前快照 |
| `PostToolUse` | `exec` | 比较快照并归属命令实际改动 |
| `Stop` | 全部停止事件 | 补 L3、同步机器字段;有新语义缺口时输出 `decision: block` 让模型补写,`stop_hook_active` 时不重复阻止 |
| `SessionEnd` | 全部会话结束 | 记录用量未知的维护账本;不再维护文件 |

Stop 自动维护只覆盖本会话可归属、仍未提交且净变化的代码文件。它不会为未采用协议的项目初始化索引;冲突、无效编码、生成文件、项目外链接和并行会话改动遵循共享引擎的跳过/隔离规则。测试仍由开发任务运行,自动维护不替代测试。

## 手动适配

不启用 hooks 时,可只注入 Devin 的 `AGENTS.md` 约定:

```bash
python3 scripts/geb_adapt.py /path/to/project --tool devin
```

Devin 按其文档读取 `AGENTS.md`,但不支持 `AGENTS.override.md`。确认 hooks 未加载时,按 [manual-workflow.md](manual-workflow.md) 的三步维护流程手动同步、检查。

## 遥测与边界

Devin hook 没有公开 transcript 或 token usage。账本位于 `${FUGUE_DATA_DIR:-~/.config/devin/fugue}/metrics/`,使用 `geb.metrics.v2`、`agent: devin`、`task: devin-session`,`usage: null` 与 `status: telemetry_unavailable`;绝不把未知记成零。没有可比基线时 savings 也保持未知。

Hooks 在 CLI/Desktop 宿主中执行,命令需要该宿主可用的 Python、技能文件和项目文件系统。云端是否执行项目 `.devin/hooks.v1.json` 未经验证;远端工作区对本地 hook 不可见时无法维护。项目 hook 文件和安装成功均不等于运行时已加载,应使用 CLI `/hooks` 核实;非 CLI/Desktop 场景应使用手动流程,除非实际确认受支持。

## 未验证项与限制

- Devin 文档确认 CLI/Desktop hooks 生命周期与配置,没有确认 Devin Cloud sessions 是否执行仓库 `.devin/hooks.v1.json`;该部署行为保持未验证。
- `edit`、`write`、`notebook_edit` 的具体 `tool_input` 文件路径字段未由文档固定。实现依次接受 `file_path`、`path`、`target_file`、`notebook_path`、`file`,实际 payload 仍需宿主核验。
- `apply_patch` 输入字段未固定。实现复用 Codex parser,接受 `command`、`patch`、`input`;如 payload 使用其他结构,补丁归属可能缺失。
- `exec` 可能在命令结束前返回,文档没有可靠的“仍在运行”信号。仅 PostToolUse 时可见的文件写入能够比较;PostToolUse 之后才发生的后台写入无法归属,Stop 的 leftover flush 只能补记已有快照里的可见变化。
- Hook payload 没有公开 transcript 或 token usage 字段,因此用量始终未知;不读取相邻会话或推算 token。
- Devin 文档不支持 `AGENTS.override.md`;适配器只写 `AGENTS.md`。PostCompaction 事件虽可注册,但没有文档化的 `additionalContext` 输出语义,故本实现不注册该事件。
- Devin 技能全局目录根据创建技能文档确认为 `~/.config/devin/skills/`;CLI 自动加载和具体组织策略仍应由使用者在宿主内确认。
