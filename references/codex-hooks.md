# Codex 原生 hooks

`geb_codex_hook.py` 将 Codex 事件适配到与 Claude Code 共用的维护引擎,`geb_codex_metering.py` 处理 Codex 本地计量。通过 `geb_install_codex.py --hooks` 显式安装,并在 Codex 原生界面审查、信任后生效。完整安装命令见 [codex.md](codex.md)。

当前接口核对基于 Codex CLI `0.159.0-alpha.3` 以及下列固定版本源码;该 CLI 的 `hooks` 功能为 stable、默认启用,不使用已过时的 `plugin_hooks` 开关。已验证源码协议与离线事件闭环,但本次执行环境的 app-server 因 `EROFS` 无法启动,尚未完成真实模型端到端验证。Desktop 和云端也需分别验证,不能从 CLI 的功能声明推断它们均已支持。

## 事件与职责

| 原生事件 | 赋格行为 |
|---|---|
| `SessionStart` | 只在已采用协议的项目记录会话起点并注入一行 L1 → L2 → L3 导航;建立可用遥测起点 |
| `SubagentStart` | 为 ThreadSpawn 子代理建立独立归属与计量起点,提供同样的索引导航 |
| `UserPromptSubmit` | 在新请求边界核对归属记录,移除被外部继续编辑的内容 |
| `PreToolUse` | 解析 `apply_patch` 的文件结构行;对 Bash/命令工具记录执行前快照 |
| `PostToolUse` | 在命令完成后对比快照,记录命令实际改动;保留异步命令的归属上下文 |
| `Stop` | 移除已提交或还原的记录,自动补缺失 L3、同步机器字段与索引,仅将本会话新产生的语义缺口返回模型继续补写,并更新计量 |
| `SubagentStop` | 对子代理执行完整维护回环、语义缺口回灌和独立计量,不依赖子代理收到 SessionEnd |
| `SessionEnd` / `Interrupt` | 补记最后可用遥测;不维护文件,不阻止会话退出或用户中断 |

原生 `apply_patch` 输入使用 `command` 字段,钩子只解析 `*** Add File`、`*** Update File`、`*** Delete File`、`*** Move to` 等结构行。Codex 的 shell 工具在原生 hook 中按 `Bash` 处理;异步命令未结束时不会发出完成后的 PostToolUse,完成时仍使用原工具调用标识。适配器也接受直接转发的 `exec_command`/`write_stdin` 事件。

Stop / SubagentStop 在需要补语义时输出原生阻止结束的结果,由 Codex 继续相应模型执行。模型只补提示中列出的 `[POS]`、`[OUTPUT]`、清单职责或目录定位。同一缺口内容不变时只提示一次,不会因遗留漂移反复阻止结束。有机器字段写入但无语义缺口时返回简短 `systemMessage` 通知;仅函数体改变且无同步写入时保持静默。相关项目测试仍由开发任务执行,自动索引维护不代替测试。

固定版本的 ThreadSpawn 子代理通过 SubagentStart / SubagentStop 进入和结束自身生命周期,不触发 SessionEnd。因此安装器注册九类事件,子代理收尾不能只依赖主会话的 Stop 或 SessionEnd。父子会话各自记录文件归属,协调并行修改时仍需避免同时编辑同一文件。

## 维护范围

钩子仅作用于已采用 GEB 的项目,不会因为安装了技能就在其他项目生成索引。会话状态有 Codex 命名空间,不与 Claude 会话混用。仅处理能归属到本会话、仍有未提交净改动的代码;用户已有改动和其他会话的改动不自动收归本会话。

共享引擎跳过合并/变基中的写入,保留冲突、语法错误、非 UTF-8、生成文件和项目外链接的现有机器字段。切分支、拉取、合并、stash 恢复等 Git 操作带来的文件也不作为本会话创作计入。工具快照的归属判断有边界:多个会话同时改同一文件时应协调编辑范围,不要把它视为跨进程的文件锁。

修改代码的后台命令应等待 `exec_command` / `write_stdin` 报告完成后再结束任务。原生命令若跨过 Stop 继续写文件,之后的改动无法可靠归属;与现有 Claude 流程一样,不承诺任意跨轮后台进程的归属跟踪。

手动 `geb_sync.py --changed` 不具有这种会话归属过滤,它覆盖仓库全部 dirty changes。钩子已启用并正常运行时,无需重复运行手动同步、检查或计量。未启用或未信任时使用 [manual-workflow.md](manual-workflow.md)。

## 信任与宿主

首次启用时在 Codex 的 **Hooks need review** 或 `/hooks` 中审查命令并确认信任;项目钩子还要求项目本身已受信任。安装器不写信任哈希、不设置 bypass、不更改 `config.toml`;配置变动后如 Codex 再次要求审查,遵循原生流程。项目和个人 hooks 会累加,同一项目只选一处注册赋格钩子。

钩子命令运行在 Codex 宿主上,需要宿主可用的 Python、技能脚本与项目路径。本地 hooks 无法修改远端不可见的工作区。linked worktree 的 hook 配置源可能来自主工作树,安装器要求显式 `--hooks-dir` 选择实际来源。技能文件存在或安装命令成功本身不代表宿主已经执行过钩子。

遇到没有自动维护的情况,依次检查原生 hooks 是否受支持、已启用和信任、配置是否来自预期目录、目标项目是否已有索引,以及宿主是否能读取项目。无需为排查计量反复运行 `doctor`,也不需要提权或跳过 Codex 的审查。

## 计量

自动计量只读取与 hook 会话 ID 绑定的本地遥测,不会从相邻会话借用数字。默认数据目录为 `${CODEX_HOME:-~/.codex}/fugue`,可通过 `FUGUE_DATA_DIR` 指定,账本位于其 `metrics/` 下。重复 Stop、SubagentStop、SessionEnd 或 Interrupt 更新对应会话的同一记录,不重复累计。

SubagentStop 的 `transcript_path` 指向父日志,`agent_transcript_path` 才是子代理日志。适配器选择后者并继续核对子代理 ID,不会将父日志计数当成子代理用量。子日志缺失或身份不符时保持 unknown/未知,父子记录独立,不自动合并为父任务总量。

缺日志、会话身份不匹配、计数重置、无法验证的日志轮换或没有新遥测时,用量保持 unknown/未知并静默继续。中途才得到日志时只记录后续有证据的区间,独立子代理会话不自动合并。自动账本按固定项目会话设计,同一 thread 跨项目切换的记录不适合汇总为独立项目收益。没有合格对照不声称节省。详细口径见 [token-accounting.md](token-accounting.md)。

## 协议来源

适配依据固定在 OpenAI Codex 提交 `2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4`:

- [hooks/src/schema.rs](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/hooks/src/schema.rs):事件标准输入与输出结构。
- [config/src/hook_config.rs](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/config/src/hook_config.rs):hooks.json 配置结构。
- [core/src/session/turn.rs](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/core/src/session/turn.rs):Stop 结果如何继续模型执行。
- [core/src/hook_runtime.rs](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/core/src/hook_runtime.rs):ThreadSpawn 的 SubagentStart / SubagentStop 生命周期、父子日志字段及 SessionEnd 边界。
- [core/src/tools/hook_names.rs](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/core/src/tools/hook_names.rs):原生工具与 hook 工具名映射。
