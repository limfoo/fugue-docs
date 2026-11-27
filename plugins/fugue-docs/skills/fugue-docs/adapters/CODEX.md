## Codex 执行约定

先遵守项目已有规则及目标目录更深层的 `AGENTS.md` / `AGENTS.override.md`,只维护当前任务涉及的文档。本规则注入本身不注册钩子;原生 Codex 钩子由 `geb_install_codex.py --hooks` 显式安装,使用 `geb_codex_hook.py`,不直接使用 Claude Code 的 `hooks/hooks.json`。

**已启用并信任原生钩子时**:会话开始自动提供索引导航,工具事件记录本会话文件归属,Stop 自动补新文件 L3、同步机器字段并将语义缺口交回模型。按“赋格:”提示补齐语义,同一未变化缺口不会重复提示。不需要再运行下方日常同步、检查或计量脚本,项目相关测试仍照常运行。未采用协议的项目不自动初始化;缺失或不匹配的遥测记为未知并静默继续。不能仅凭技能或 hooks.json 存在认定钩子已生效,首次使用需由用户完成 Codex 自身的 Hooks need review 或 `/hooks` 信任审查。

**工具定位**:优先使用已加载的 `$fugue-docs` 技能目录下的 `scripts/`;否则依次检查项目 `.agents/skills/fugue-docs/scripts/`、项目 `scripts/geb/`、个人 `~/.agents/skills/fugue-docs/scripts/`。确认 `geb_sync.py` 和 `geb_check.py` 存在后,把其所在目录作为下面的 `<tools-dir>`。路径含空格时保留双引号。不要假定当前工作目录就是技能目录,也不要假定用户项目中有本仓库的 `scripts/`。

**未启用钩子时的开发回环**:

1. 先查看工作区已有改动,再读 L1 → 目标 L2 → 文件头和相关代码。已有索引按实际变更维护;只读任务不初始化索引。
2. 改代码后,先预演 `python3 "<tools-dir>/geb_sync.py" "<root>" --changed --dry-run`,确认范围后去掉 `--dry-run`。`--changed` 包含整个工作区的未提交变更,不是会话归属列表;非 Git 项目会回退全量。有用户或其他代理的混合改动时,仅编辑本任务对应的文件头和索引条目,不要直接执行会覆盖无关内容的同步。新增文件需补齐 L3,同步器不会生成缺失的头部。
3. 补齐本次变更的 `[OUTPUT]`、`[POS]` 和清单职责,结构变化时更新 L1。运行 `python3 "<tools-dir>/geb_check.py" "<root>" --strict --complete --report` 和项目相关测试,如实报告遗留问题。

需要初始化时,先运行同目录的 `geb_arch.py` 和 `geb_scaffold.py --dry-run`,再按已授权范围生成骨架、读代码并补齐语义。缺少工具时报告缺失,使用上述目录中的已安装副本,或按安装说明用 `geb_adapt.py --tool codex --copy-tools` 安装配套工具;不下载或执行未经检查的远端脚本。

**计量**:启用钩子后自动记录可用本地遥测,默认账本为 `${CODEX_HOME:-~/.codex}/fugue/metrics`,`FUGUE_DATA_DIR` 可改数据目录。未启用钩子时,仅在用户要求且本地遥测可读、账本可写时使用 `geb_metrics.py start/finish`。云环境缺少日志或沙箱禁止访问时记为未知并继续任务,不为计量提权或反复诊断。不要把未计量写成零,没有有效对照不声称节省 token。
