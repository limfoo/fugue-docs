# Codex 接入

需要 Python 3.9+。Codex 可以使用原生技能,并选择安装原生 hooks 获得自动维护流程。当前接口验证基于 Codex CLI `0.159.0-alpha.3`(`hooks` 显示为 stable、默认启用),不需要旧的 `plugin_hooks` 开关。CLI、Desktop 或云端宿主的能力与可见文件系统可能不同,不能据此宣称所有环境都已实测。

## 原生技能与自动钩子

从本仓库目录运行以下命令,将 `/path/to/project` 替换为目标项目根目录:

```bash
python3 scripts/geb_install_codex.py --project /path/to/project --hooks --dry-run
python3 scripts/geb_install_codex.py --project /path/to/project --hooks
```

技能安装到 `/path/to/project/.agents/skills/fugue-docs`,钩子写入 `/path/to/project/.codex/hooks.json`。重新打开项目或开始新会话,在 Codex 的 **Hooks need review** 或 `/hooks` 中审查并信任这些命令;项目钩子还要求项目本身已被 Codex 信任。安装器不预填信任哈希、不绕过审查,也不修改 `config.toml`。确认技能可用且钩子已启用后,已有索引的项目会自动维护,日常开发无需手动调用技能或运行同步、检查、计量脚本。

首次接入时可显式输入:

```text
$fugue-docs 为当前项目初始化索引。
```

安装本身不初始化索引。初始化遵循 [SKILL.md](../SKILL.md) 的架构分析、骨架预览、补语义和校验流程。未采用协议的项目不自动维护,只读审查不生成索引。

其他安装范围按需选择。项目和个人 hooks 会累加,同一项目不要在两层重复注册赋格钩子:

```bash
# 个人技能: ~/.agents/skills/fugue-docs
# hooks: ${CODEX_HOME:-~/.codex}/hooks.json
python3 scripts/geb_install_codex.py --user --hooks

# 自定义完整技能目录;使用 --hooks 时还须显式指定 hooks 所在目录
python3 scripts/geb_install_codex.py --dest /path/to/skills/fugue-docs --hooks --hooks-dir /path/to/project/.codex

# 更新同一目标的已有安装,先预览再应用
python3 scripts/geb_install_codex.py --project /path/to/project --hooks --update --dry-run
python3 scripts/geb_install_codex.py --project /path/to/project --hooks --update
```

`--project`、`--user`、`--dest` 三选一。`--hooks-dir` 也可覆盖项目或个人 hooks 的默认位置,但只能与 `--hooks` 一起使用。自定义目录不保证被 Codex 发现;需选择实际宿主读取的位置。linked worktree 的默认 `--project --hooks` 安装会被拒绝,需用 `--hooks-dir` 显式指定 Codex 实际读取的主工作树配置目录。

`--dry-run` 输出技能目录、受管文件数和 hooks.json 位置,不写文件。安装仅复制白名单文件,不带 Claude 的 `.claude-plugin/` 或 `hooks/`;Codex hooks.json 单独生成,使用 `geb_codex_hook.py`。不注册 Claude 钩子、pre-commit 或 CI,不改 Git 配置。

`--update` 仅更新未被本地修改的受管文件与 hook 条目,保留其他 hooks 和配置说明。相邻 `.fugue-codex-hooks.json` 记录受管条目。已修改、移除或重复的条目会报冲突;`config.toml` 已引用 `geb_codex_hook.py` 时也会拒绝重复注册。先保留本地编辑并处理冲突,不强制覆盖。目前没有自动卸载参数。

自动流程是:会话导航 → 工具事件记录本会话改动 → Stop / SubagentStop 补 L3、同步机器字段 → 语义缺口回灌模型继续补写。同一未变化缺口只提示一次。ThreadSpawn 子代理通过 SubagentStart / SubagentStop 获得独立维护与计量,不依赖 SessionEnd。事件协议、并行编辑边界和排查说明见 [codex-hooks.md](codex-hooks.md)。

## 不安装钩子

省略 `--hooks` 即保持默认的原生技能安装,不会写 hooks.json:

```bash
python3 scripts/geb_install_codex.py --project /path/to/project
```

此时可用 `$fugue-docs 检查并维护当前项目索引` 调用技能,按 [manual-workflow.md](manual-workflow.md) 手动同步、检查。不要仅凭技能已发现就假定钩子已生效。

## 只接入项目规则

未安装原生技能、但希望项目携带协议与脚本时,从本仓库运行:

```bash
python3 scripts/geb_adapt.py /path/to/project --tool codex --copy-tools --dry-run
python3 scripts/geb_adapt.py /path/to/project --tool codex --copy-tools
```

适配器将协议与 Codex 手动维护步骤写入托管块,优先使用目标根目录已有的 `AGENTS.override.md`(包括空文件),否则使用 `AGENTS.md`;保留其他规则内容。同目录有 override 时 Codex 优先选择它,既有 `AGENTS.md` 文件仍保留。`--copy-tools` 提供项目内可运行的脚本,不会安装原生技能,因此不能用它代替技能发现验证。已安装原生技能时可直接使用技能内脚本,通常无需复制。

规则适配器不注册原生钩子。未另行启用钩子时,日常同步和检查按 [manual-workflow.md](manual-workflow.md) 手动执行。`geb_sync.py --changed` 涵盖仓库全部未提交改动,先 `--dry-run` 核对范围;多代理或用户已有改动混在一起时,只维护本次负责内容,不全量覆盖。提交检查或 CI 仅在用户要求时另加 `--pre-commit`、`--ci`。

## 计量与宿主边界

原生钩子自动记录本机当前会话的可用遥测,默认写入 `${CODEX_HOME:-~/.codex}/fugue/metrics`;`FUGUE_DATA_DIR` 覆盖数据目录,账本在其 `metrics/` 下。缺少日志、身份不匹配或日志轮换无法验证时用量为 unknown/未知,静默继续。没有合格对照时节省量也为未知。未注册钩子时,手动计量仍只在用户要求且日志可读、账本可写时启用。详见 [token-accounting.md](token-accounting.md)。

hooks 在 Codex 宿主上执行。本机钩子无法维护宿主看不到的远端工作区;本地安装也不会自动同步到远程或网页会话。Desktop/云端需分别确认事件支持、配置与技能发现、Python 和项目文件可访问性。缺失能力时使用手动流程,不要为计量反复运行 `doctor` 或请求提权。
