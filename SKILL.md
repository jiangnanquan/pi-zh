---
name: q-zh-pi
description: Pi Agent CLI（@earendil-works/pi-coding-agent）终端界面简体中文汉化与第三方插件简介运行时覆盖。核心工作流：基于干净备份安全打补丁 → node --check 语法校验 → 插件简介零侵入软链字典 → 四项冒烟验收；支持上游发版后增量适配与一键还原官方英文，版本号严格跟随官方。适用场景：「汉化 pi」「更新 pi 汉化」「pi 汉化失效」「检查 pi 汉化状态」「还原 pi 官方英文」「插件简介变回英文了」。红线约定：只汉化 CLI/TUI 展示文本（命令描述、参数提示、设置菜单、状态栏、插件简介），命令名与 flags 锁定英文原文，不碰模型请求 payload、上下文管理、协议逻辑与插件源码。
---

# Pi Agent CLI 汉化（q-zh-pi）

把 [Pi Agent CLI](https://github.com/badlogic/pi-mono)（npm 全局包 `@earendil-works/pi-coding-agent`）的
CLI/TUI 展示文本汉化为简体中文，并让第三方插件在 `/` 补全面板中的英文简介显示为中文。

**本项目只做界面汉化这一件事。** 模型请求 payload、上下文管理、RPC/CBOR 协议、插件源码与业务逻辑一律不碰。

本文件位于仓库根目录，仓库根目录即技能目录：`scripts/`、`i18n/`、`tests/` 均以相对路径引用，
任何 AI 读完本文件即可独立完成全部维护动作。

## 项目简介与核心原则

| # | 原则 | 约束 |
| :--- | :--- | :--- |
| 1 | 命令原名绝对锁定 | 命令 `name` 与 flags 禁止汉化，仅译 `description` / `argumentHint` |
| 2 | 单一事实来源 | 所有翻译事实维护在 `i18n/*.json`，脚本中禁止硬编码补丁文本 |
| 3 | 干净基底 | 首次打补丁前留存官方原件 `.zh-backup`；备份已存在时以备份为读取源，绝不覆盖 |
| 4 | 语法安全沙箱 | 每次写入后用 `node --check` 校验，失败立即原子回滚，不产生半成品文件 |
| 5 | 版本严格跟随 | `pi --version` 显示上游官方版本号，不自造版本 |
| 6 | 插件零侵入 | 插件简介走「运行时覆盖 + `i18n/plugins.json` 字典映射」，不改 `node_modules` 任何文件 |

当前适配基准：Pi `0.85.1`（以 `scripts/patch_engine.py` 的 `SUPPORTED_VERSIONS` 为唯一权威）。

## 快速开始（一键命令）

所有命令均以仓库根为工作目录执行（前置依赖：`python3`、`node`、已全局安装的 `pi`）：

```bash
cd /Users/jnq/Dev/Private/pi-zh

# ① 一键应用 CLI/TUI 汉化：寻址全局 pi → 留存干净备份 → 打补丁 → node --check → 自动执行四项冒烟
bash scripts/apply_patch.sh

# ② 一键安装插件简介汉化：把运行时覆盖扩展与翻译字典软链到 ~/.pi/agent（幂等，可重复执行）
bash scripts/install_plugin_i18n.sh
```

插件汉化完成后，在 pi 会话内执行 `/reload`（或重启 pi）即可看到中文简介；CLI 汉化无需重载。

## 状态检查与冒烟验收

```bash
cd /Users/jnq/Dev/Private/pi-zh

bash scripts/smoke_test.sh                    # 四项冒烟：版本号 / 中文帮助 / 插件字典一致性 / 运行时覆盖端到端
bash scripts/apply_patch.sh --status          # 本体汉化状态：官方原版 or 已应用（统计 .zh-backup）
bash scripts/install_plugin_i18n.sh --status  # 插件汉化状态：软链健康度 + 字典覆盖数 + 与已装插件差异
python3 scripts/scan_plugin_commands.py --check   # 插件简介漂移检查：新增 / 原文漂移 / 字典残留
```

人工确认项：终端启动 `pi`，依次查看 `pi --help`、`/help`、`/model`、`/settings` 与 `/` 补全面板——
展示应为中文，且所有命令名、flags 保持英文原文。

## 分步操作规程

两条维护线互相独立，只有维护线 A 需要重打补丁：

| 维护线 | 触发条件 | 入口命令 | 需要重打补丁 |
| :--- | :--- | :--- | :--- |
| A. Pi 本体汉化 | 上游发布新版本 | `bash scripts/apply_patch.sh` | 是（先更新版本适配清单） |
| B. 插件简介汉化 | 插件升级 / 新增插件 | `python3 scripts/scan_plugin_commands.py --check` | 否（运行时覆盖，只增量补字典） |

### A. Pi 本体汉化：上游发版后的增量适配

**A1. 升级本地官方包并确认版本**

```bash
npm update -g @earendil-works/pi-coding-agent
pi --version
```

**A2. 将新版本号追加进适配清单**

编辑 `scripts/patch_engine.py`：

```python
SUPPORTED_VERSIONS = ["0.85.1", "0.86.0"]
```

**A3. Dry-run 检测命中率**

```bash
python3 scripts/patch_engine.py --dry-run
```

- 核对替换数量与未命中项；官方新增命令、快捷键或设置项时，先补齐对应字典：
  `i18n/commands.json` / `i18n/keybindings.json` / `i18n/settings.json` / `i18n/cli.json` / `i18n/ui.json`。
- 若报「版本不在已知适配清单」，返回 A2；`--force` 只是应急逃生舱，使用前必须说明理由并人工复核 dry-run 结果。

**A4. 全量应用并验收**

```bash
bash scripts/apply_patch.sh
```

该脚本末尾自动执行 `scripts/smoke_test.sh`，四项全绿才算完成。

**A5. 一键还原官方英文原版**

```bash
bash scripts/apply_patch.sh --restore
```

还原后 `pi --help` 立即恢复英文，`pi --version` 仍显示官方版本号。

### B. 插件简介汉化：运行时增量补译

插件升级会重写 `node_modules` 文件，但翻译走运行时覆盖，**汉化不会失效**；
只有插件改动简介文案或新增命令时，才需要增量维护字典。

**B1. 查看漂移**

```bash
python3 scripts/scan_plugin_commands.py --check
```

| 输出类型 | 含义 | 处置 |
| :--- | :--- | :--- |
| 新增未翻译 | 插件新增了命令 | 在 `i18n/plugins.json` 中补 `en` / `zh` 条目 |
| 原文漂移 | 插件改了简介措辞 | 同步 `en`（否则该命令回退英文显示），校对 `zh` |
| 字典残留 | 插件删了命令 | 从字典中删除对应条目 |

**B2. 刷新基线（仅改措辞时使用）**

```bash
python3 scripts/scan_plugin_commands.py --update-baseline
```

只刷新 `en` 原文并把新命令登记为 `zh` 空串（空串自动跳过、保持英文），已译 `zh` 不会被覆盖。

**B3. 补齐翻译并验收**

```bash
python3 tests/test_plugin_i18n.py    # 字典契约与扫描器测试
node tests/test_plugin_i18n.mjs      # 运行时覆盖端到端契约测试
bash scripts/smoke_test.sh           # 全量冒烟（含插件项）
```

**B4. 安装 / 修复 / 卸载**

```bash
bash scripts/install_plugin_i18n.sh              # 安装或修复软链（幂等）
bash scripts/install_plugin_i18n.sh --force      # 链接位被占用时强制替换（确认后使用）
bash scripts/install_plugin_i18n.sh --uninstall  # 卸载，插件简介立即恢复英文
```

软链落点为 `~/.pi/agent/extensions/plugin-i18n.ts` 与 `~/.pi/agent/plugin-i18n/plugins.json`；
可用环境变量 `PI_AGENT_DIR` 覆盖默认的 `~/.pi/agent`。

## 常见避坑点与故障排查

| 现象 | 原因 | 处置 |
| :--- | :--- | :--- |
| 运行 `pi` 报 `SyntaxError` | 某条翻译含未转义引号 | 引擎的 `node --check` 会拦截并原子回滚；检查 `i18n/*.json` 引号转义，必要时 `bash scripts/apply_patch.sh --restore` |
| 「未检测到已安装的 pi」 | 当前 Shell 未加载全局 Node bin（fnm / nvm / mise） | 先 `which pi` 确认；或显式指定 `python3 scripts/patch_engine.py --apply --pkg-dir "/path/to/@earendil-works/pi-coding-agent"` |
| 版本不在适配清单、打补丁被拒 | 上游已发版但未更新 `SUPPORTED_VERSIONS` | 走维护线 A2；`--force` 仅限应急并需人工复核 dry-run 结果 |
| `/` 面板插件简介变回英文 | ① 插件改了措辞；② 软链被清理或指向异常；③ 刚升级插件未重载；④ 该命令是内置命令或提示词模板（不在插件汉化范围） | ① 跑 `--check` 同步 `en` / `zh`；② `install_plugin_i18n.sh --status` 后重跑安装脚本（幂等）；③ 会话内执行 `/reload`；④ 属正常现象，不处理 |
| 重复打补丁是否会污染基底 | 不会 | 引擎始终以 `.zh-backup` 干净原件为源；已存在备份时绝不重新覆盖 |
| 插件简介汉化会影响模型请求或插件行为吗 | 不会 | 仅改写补全面板展示用的 `description` 字符串，不触碰命令名、参数、工具定义与请求 payload；卸载后立即恢复原样 |

## 红线清单（违反即返工）

| 红线类别 | 违规案例 | 正确做法 |
| :--- | :--- | :--- |
| 命令名汉化 | `name: "compact"` 改为 `name: "压缩"` | 保留 `name: "compact"`，仅替换 `description` |
| 污染代码标识符 | 变量 `defaultProjectTrust` 被替换为 `defaultProject信任` | 单词替换必须用正则限定在引号字面量内匹配 |
| 覆盖干净基底 | 重复打补丁时覆盖了原有的 `.zh-backup` | 已存在备份时以备份为读取源，绝不重新备份 |
| 破坏版本号 | 把 `pi --version` 改为 `pi-zh 1.0` | 严格保留官方原始版本（如 `0.85.1`） |
| 改写插件源码 | 直接编辑 `node_modules` 中插件的 `description` | 仅允许「运行时覆盖 + `i18n/plugins.json` 字典映射」 |
| 越界翻译 | 翻译插件 `registerTool` 的工具描述或 skill 描述 | 工具描述会进模型请求 payload，一律不碰 |

## 完成定义（DoD，一次合格交付的全部验收项）

```bash
cd /Users/jnq/Dev/Private/pi-zh

python3 tests/test_patch.py            # ① CLI 汉化单元测试与红线隔离测试
python3 tests/test_plugin_i18n.py      # ① 插件字典契约与扫描器测试
node tests/test_plugin_i18n.mjs        # ① 运行时覆盖扩展端到端契约测试
bash scripts/apply_patch.sh            # ② 补丁应用无报错（含 node --check 语法校验）
bash scripts/smoke_test.sh             # ③ 四项冒烟全部通过
bash scripts/apply_patch.sh --restore              # ④ 还原可用：pi --help 恢复英文
bash scripts/install_plugin_i18n.sh --uninstall    # ④ 插件汉化可卸载：简介恢复英文
```

最后确认代码与配置中无敏感凭据、个人路径或测试脏文件残留。

## 关键文件速查

- **翻译事实源（`i18n/`，唯一事实来源）**
  - `commands.json` — 斜杠命令（`name` 锁原文，译 `description` / `argumentHint`）
  - `keybindings.json` — 快捷键说明
  - `settings.json` — 交互设置菜单选项
  - `cli.json` — `pi --help` 参数与帮助文本
  - `ui.json` — TUI 状态栏与交互短语
  - `plugins.json` — 第三方插件命令简介（`source` / `en` / `zh` 三元组）
- **执行脚本（`scripts/`）**
  - `apply_patch.sh` — 一键应用 / 状态 / 还原 / dry-run 入口
  - `patch_engine.py` — 补丁引擎（安全匹配、备份管理、`node --check` 校验、`SUPPORTED_VERSIONS`）
  - `install_plugin_i18n.sh` — 插件简介汉化：安装 / 状态 / 卸载
  - `scan_plugin_commands.py` — 插件命令扫描与翻译漂移检查
  - `smoke_test.sh` — 四项冒烟测试
- **测试（`tests/`）**
  - `test_patch.py`、`test_plugin_i18n.py`、`test_plugin_i18n.mjs`
- **文档**
  - `SOP.md` — 升级与维护标准操作手册（详细分步流程）
  - `AGENTS.md` — AI 维护契约、红线清单与完成定义
  - `00_状态.md` — 时空胶囊状态卡（当前基线 / 翻译条目规模 / 下一步）
  - `extensions/plugin-i18n.ts` — 插件简介运行时覆盖扩展
