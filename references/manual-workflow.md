# 手动维护流程(没有钩子的工具)

Codex 原生钩子已启用并通过信任审查、或 Claude Code 已启用 fugue-docs 插件钩子时,日常维护与计量由钩子自动完成,无需重复本文件的同步、检查和计量脚本。模型只响应本轮语义提示,项目本身的测试仍需按任务执行。未安装、未信任或当前宿主不支持钩子时,按本文件手动执行。`<skill-dir>` 是 SKILL.md 所在目录,`<root>` 是项目根目录;优先调用技能内的工具,不假定用户项目已经复制了 `scripts/`。Codex 安装与显式调用见 [codex.md](codex.md),自动流程见 [codex-hooks.md](codex-hooks.md)。

## 开始开发

1. 读取适用的 `AGENTS.md`、`AGENTS.override.md` 和项目自身规则,再读 L1、目标目录 L2 和相关文件头定位代码。索引不能替代修改前对相关实现的阅读。只读审查不初始化文档;未采用协议的项目仅在用户要求接入时初始化。
2. 用 `git -C "<root>" status --short` 了解已有改动,记录本次任务负责的文件。用户和其他代理的编辑不属于本次任务,不回滚或顺带重写。非 Git 项目也要明确允许修改的范围。
3. 保留已有规则,协议段采用追加或托管块更新。计量不是开发前置条件;用户要求计量时按下方可选流程操作。

## 维护与收尾

1. 代码修改后先运行 `python3 "<skill-dir>/scripts/geb_sync.py" "<root>" --changed --dry-run` 并核对 Git diff。`--changed` 包含仓库全部 staged、unstaged 和 untracked 改动,不是当前 Codex 会话的文件归属过滤器。非 Git 项目会回退全量。确认所有将写入的文件都在任务范围内,再去掉 `--dry-run` 执行;混有用户或其他代理的编辑时,只人工维护本次负责的文件和必要索引条目,不要直接执行仓库级同步覆盖混合改动。首次接入或处理历史漂移的全量同步也须先预览并确认范围。清单职责与非代码条目由人维护;依赖和代码行集合由机器维护。
2. 检查所改文件的 `[OUTPUT]`、`[POS]` 和模块职责,结构变化时更新 L1。`--graph` 显式重绘依赖图,使用前核对是否会替换人工图。
3. 运行 `python3 "<skill-dir>/scripts/geb_check.py" "<root>" --strict --complete --report` 以及项目本身的相关测试。报告实际通过、遗留或无法验证的情况,不把结构检查当语义正确证明。
4. 最终回复简述索引修改与校验结果。仅在本次实际启用了计量时附计量结果;不要为收尾补造用量或声称未经测量的节省。

## 可选计量

仅在用户要求、当前环境有受支持的可读 Codex 本地会话日志且账本目录可写时运行:

1. 开始时执行 `python3 "<skill-dir>/scripts/geb_metrics.py" start "<root>" --task "<本次任务短标识>"`。保留 `run_id`,检查 `measurement_ready`。默认账本为 `~/.codex/fugue/metrics`;用户指定可写位置时可在子命令前加 `--ledger <目录>`。
2. `measurement_ready` 为 false 或当前环境没有本地日志时,将用量标记为 unknown/未知并继续开发。需要排查时可运行一次 `doctor`,不要重复探测,不要为计量请求提权或阻塞任务。
3. 已成功开始计量时执行 `python3 "<skill-dir>/scripts/geb_metrics.py" finish "<run_id>" --receipt`,自定义账本须使用同一 `--ledger`。有测试日志时传 `--outcome passed|failed|partial --evidence <文件>` 绑定验收依据。收据只覆盖记录区间,不含之后回复与未汇总的独立子会话。

计量只记录实际用量。没有可比对照时,节省量保持 `null`,不能把缓存命中、字符压缩比或没读的文件数记成已节省 token。需要衡量收益或查看跨项目账本时读 [token-accounting.md](token-accounting.md)。

## 可选提交约束

用户要求安装提交检查或团队 CI 时,先用 `python3 "<skill-dir>/scripts/geb_adapt.py" "<root>" --tool codex --pre-commit --ci --dry-run` 预览,再去掉 `--dry-run` 应用。提交钩子检查暂存快照;已有非托管钩子会保留并生成待合并旁路文件,安装输出须如实说明。普通开发不改全局 Git 配置或覆盖已有钩子。
