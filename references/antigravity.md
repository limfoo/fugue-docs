# Antigravity 接入说明 (`fugue-docs-agy`)

需要 Python 3.9+（零第三方依赖），跨平台支持 Windows、macOS 与 Linux。本仓库的 `feat/antigravity-plugin` 分支根目录本身即为合法的 Antigravity 原生插件，同时提供精简安装脚本 `scripts/geb_install_antigravity.py`。

## 快速安装

### 方式一：一行 `git clone` 极速安装（推荐，支持 `git pull` 一键升级）

- **macOS / Linux**：
  ```bash
  git clone -b feat/antigravity-plugin https://github.com/limfoo/fugue-docs.git ~/.gemini/config/plugins/fugue-docs-agy
  ```
- **Windows (PowerShell)**：
  ```powershell
  git clone -b feat/antigravity-plugin https://github.com/limfoo/fugue-docs.git "$env:USERPROFILE\.gemini\config\plugins\fugue-docs-agy"
  ```

安装后 Antigravity 会自动发现并默认启用该插件（无需重启，下一轮对话生效）；后续升级只需在插件目录执行 `git pull`。

### 方式二：使用精简安装器（仅复制运行必需文件，不含 `evals/` 等开发目录）

```bash
# 预览并安装到用户全局插件目录 (~/.gemini/config/plugins/fugue-docs-agy)
python3 scripts/geb_install_antigravity.py --user --dry-run
python3 scripts/geb_install_antigravity.py --user

# 或安装到单个项目的 .agents/plugins/fugue-docs-agy
python3 scripts/geb_install_antigravity.py --project /path/to/project
```
（Windows 下将 `python3` 替换为 `python`。）

### 校验插件合规性

```bash
agy plugin validate ~/.gemini/config/plugins/fugue-docs-agy --strict
```

## 事件映射与职责

| Antigravity 事件 | 匹配范围 | 赋格行为 |
| :--- | :--- | :--- |
| `SessionStart` | 全部会话 | 仅对已存在 `PROJECT_INDEX.md` 的项目保存状态，并通过 `injectSteps.systemMessage` 注入一行索引导航提示 |
| `PreInvocation` | 每次模型调用前 | 在回合首轮清理被外部修改的文件归属，并记录工作区基线快照 |
| `PostToolUse` | `write_file` / `edit_file` / `write_to_file` / `replace_file_content` / `multi_replace_file_content` / `run_command` | 零权限侵入地归属本会话改动的文件，并在命令执行后比对快照 |
| `Stop` | 回合结束 | 自动补齐新文件 L3 骨架、增量同步 `[INPUT]` 与清单表；仅当 `terminationReason == "NO_TOOL_CALL"` 且 `continuationActive == false` 且存在新语义缺口时，返回 `decision: "continue"` 提示补写 |

## 跨平台与安全边界

- **跨平台解释器解析**：`hooks.json` 使用 `python ... || python3 ... || py -3 ...` 并在脚本入口内置 Python 2→3 自动 `execvp` 切换，同时兼容 Windows (`cmd /c`) 与 macOS/Linux (`sh -c`)。
- **零权限侵入**：本插件不注册 `PreToolUse`，因此不会覆盖或绕过 Antigravity 的工具权限审批策略（`allow`/`ask`/`deny`）。
- **非正常终止放行**：当用户取消（`USER_CANCELED`）、发生错误（`ERROR`）或达到步数上限（`MAX_INVOCATIONS`）时，钩子绝不拦截收工。
- **静默容错**：任意异常均写入 `~/.gemini/fugue/hook-errors.log` 并返回 `{}`，不会阻塞正常对话。
- **避免双注册**：如已启用全局插件 `~/.gemini/config/plugins/fugue-docs-agy`，请勿在单个项目的 `.agents/hooks.json` 或 `.agents/plugins/` 中重复登记相同钩子。
