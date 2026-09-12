---
name: q-zh-pi
description: Pi Agent CLI（@earendil-works/pi-coding-agent）终端界面简体中文汉化、第三方插件简介运行时覆盖与插件渲染文案（欢迎页）补丁。核心工作流：基于干净备份安全打补丁 → node --check / jiti 加载语法校验 → 插件简介零侵入软链字典 → 五项冒烟验收；支持上游发版后增量适配与一键还原官方英文，版本号严格跟随官方。适用场景：「汉化 pi」「更新 pi 汉化」「pi 汉化失效」「检查 pi 汉化状态」「还原 pi 官方英文」「插件简介变回英文了」「汉化欢迎页」「欢迎页变回英文」。红线约定：只汉化 CLI/TUI 展示文本（命令描述、参数提示、设置菜单、状态栏、插件简介、插件欢迎页文案），命令名与 flags 锁定英文原文，不碰模型请求 payload、上下文管理与协议逻辑；插件渲染行为（含布局）只在用户逐条授权下走 code_patches 通道（当前 3 条：editor 边框跟随思考色、欢迎页空壳先行、dock 去空白占位行）。
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
| 6 | 插件简介零侵入 | 插件斜杠命令简介走「运行时覆盖 + `i18n/plugins.json` 字典映射」，不改 `node_modules` 任何文件 |
| 7 | 插件渲染文案最小补丁 | 无注册接口可拦截的渲染文案（欢迎页等）走「精确字面量补丁 + `.zh-backup` + jiti 体检 + 一键还原」，只动字符串与模板片段 |
| 8 | 行为补丁授权通道 | C 线原则上只改文案；确需改插件行为（当前 3 条：editor 边框色、欢迎页空壳先行、dock 去空白占位行）时必须走 `code_patches`：带 `id`/`reason`/`authorized_on`、保留原实现作回退分支、共用预检与还原；每条都要有 pty 探针回归验证 |

当前适配基准：Pi `0.85.1`（以 `scripts/patch_engine.py` 的 `SUPPORTED_VERSIONS` 为唯一权威）。

## 快速开始（一键命令）

所有命令均以仓库根为工作目录执行（前置依赖：`python3`、`node`、已全局安装的 `pi`）：

```bash
cd /Users/jnq/Dev/Private/pi-zh

# ① 一键应用 CLI/TUI 汉化：寻址全局 pi → 留存干净备份 → 打补丁 → node --check → 自动执行四项冒烟
bash scripts/apply_patch.sh

# ② 一键安装插件简介汉化：把运行时覆盖扩展与翻译字典软链到 ~/.pi/agent（幂等，可重复执行）
bash scripts/install_plugin_i18n.sh

# ③ 一键汉化插件渲染文案（欢迎页）：备份基底 → 精确替换 → jiti 加载体检 → 渲染行宽断言
bash scripts/apply_plugin_ui.sh
```

插件汉化完成后，在 pi 会话内执行 `/reload`（或重启 pi）即可看到中文简介；CLI 汉化无需重载。

## 状态检查与冒烟验收

```bash
cd /Users/jnq/Dev/Private/pi-zh

bash scripts/smoke_test.sh                        # 五项冒烟：版本号 / 中文帮助 / 插件字典一致性 / 运行时覆盖端到端 / 插件 UI 汉化
bash scripts/apply_patch.sh --status              # 本体汉化状态：官方原版 or 已应用（统计 .zh-backup）
bash scripts/install_plugin_i18n.sh --status      # 插件简介状态：软链健康度 + 字典覆盖数 + 与已装插件差异
python3 scripts/scan_plugin_commands.py --check   # 插件简介漂移检查：新增 / 原文漂移 / 字典残留
bash scripts/apply_plugin_ui.sh --check           # 插件 UI 文案漂移检查：字典是否全部命中（不写盘）
bash scripts/apply_plugin_ui.sh --status          # 插件 UI 汉化状态：官方原版 or 已汉化（备份完好）
```

人工确认项：终端启动 `pi`，依次查看 `pi --help`、`/help`、`/model`、`/settings` 与 `/` 补全面板——
展示应为中文，且所有命令名、flags 保持英文原文。

## 分步操作规程

两条维护线互相独立，只有维护线 A 需要重打补丁：

| 维护线 | 触发条件 | 入口命令 | 需要重打补丁 |
| :--- | :--- | :--- | :--- |
| A. Pi 本体汉化 | 上游发布新版本 | `bash scripts/apply_patch.sh` | 是（先更新版本适配清单） |
| B. 插件简介汉化 | 插件升级 / 新增插件 | `python3 scripts/scan_plugin_commands.py --check` | 否（运行时覆盖，只增量补字典） |
| C. 插件 UI 汉化 | 插件升级 / 改了渲染文案 | `bash scripts/apply_plugin_ui.sh --check` | 是（补丁式，幂等重打；基底始终取自 `.zh-backup`） |

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

### C. 插件 UI 汉化：渲染文案补丁（欢迎页等）

有些插件文案在**渲染期硬编码**（如 `pi-powerline-footer` 的欢迎页 `welcome.ts`），没有任何注册接口可拦截，
运行时覆盖做不到，只能对插件源文件打精确字面量补丁。汉化条目全部维护在 `i18n/plugin-ui.json`。

```bash
bash scripts/apply_plugin_ui.sh              # 应用：备份基底 → 精确替换 → jiti 加载体检 → 渲染行宽断言
bash scripts/apply_plugin_ui.sh --check      # 漂移检测：字典是否全部命中（不写盘）
bash scripts/apply_plugin_ui.sh --status     # 状态：官方原版 / 已汉化（备份完好）
bash scripts/apply_plugin_ui.sh --restore    # 还原：欢迎页立即恢复英文
bash scripts/apply_plugin_ui.sh --dry-run    # 模拟：只看会替换多少处，不写文件
python3 tests/test_plugin_ui.py              # 单测：幂等 / 干净基底 / 未命中拦截 / 可还原
```

**C1. 上游插件发版后**

```bash
bash scripts/apply_plugin_ui.sh --check      # 未命中条目就是上游改动的文案
```

- 全部命中 → 直接 `bash scripts/apply_plugin_ui.sh` 幂等重打（基底永远取自 `.zh-backup`，不会叠加）；
- 有未命中 → 人工核对上游新原文，更新 `i18n/plugin-ui.json`（`en` 同步为上游新措辞、`zh` 重新校对），
  重跑 `--check` 直至全绿；
- 插件被 npm 重装时 `.zh-backup` 会一并消失，此时以当前官方文件为新基底重新备份，属正常现象。

**C2. 新增条目时的三条硬约束**

1. `en` 必须用 `grep` 确认在目标文件中唯一命中；
2. 短词（`Tips`、`Loaded` 等）一律用 `literal` 模式（只命中引号内字面量），严禁 `raw` 模式裸单词替换；
3. `raw` 模式必须自带足够上下文（如 `${dim("/")} for commands`、`context file${contextFiles !== 1 ? "s" : ""}`），
   以便上游改措辞时立即报漂移，而不是静默改错。

**C2b. 行为补丁（`code_patches`，例外通道）**

C 线原则上只改文案。确实需要改动插件渲染行为时，改动进 `i18n/plugin-ui.json` 的 `code_patches`，
与文案共用同一个引擎、同一份备份、同一个 `--restore`。当前共 3 条，均由用户逐条授权：

| `id` | 授权日 | 改了什么 | 回归探针 |
| :--- | :--- | :--- | :--- |
| `editor-chrome-thinking-border` | 2026-09-12 | editor 上下边框从硬编码 244 灰改为继承 pi 的 `borderColor`（thinking 色），保留灰色回退 | `scripts/probe_editor_border.py` |
| `welcome-header-eager-shell` | 2026-09-13 | 启动欢迎页先用空数据挂 header 立即上屏，取数完成后再换 header 重绘 | 目视启动过程（无独立探针） |
| `dock-trim-primary-into-footer` | 2026-09-13 | `placement=below` 时主状态行改由 footer 槽位渲染，消掉空壳 footer 白占的一行 | `scripts/probe_dock_rows.py` |

示例（`editor-chrome-thinking-border`）：

```json
{
  "id": "editor-chrome-thinking-border",
  "authorized_on": "2026-09-12",
  "reason": "为什么必须改、依据是什么",
  "from": "  const borderColor = getFgAnsiCode(\"sep\");\n",
  "to": "  const piBorderColor = Reflect.get(editor as object, \"borderColor\");\n"
}
```

四条硬约束：① `id` / `reason` / `authorized_on` 缺一不可（引擎会校验）；② `from` 必须自带上下文（≥ 30 字符）；
③ **保留原实现作为回退分支**，不删原逻辑；④ 未授权的逻辑改动禁止入字典。

行为补丁必须用探针回归 —— jiti 体检只能证明“能加载”，证明不了“边框真的变紫了”“那一行空白真的没了”：

```bash
python3 scripts/probe_editor_border.py    # 边框色：在 pty 中真启一次 pi，统计紫/灰边框行并给出判定
python3 scripts/probe_dock_rows.py        # dock 行数：解码最终帧，断言状态行即屏幕最后一行、无重复、无回显行
```

实测基线（powerline 0.17.1 / thinking=max）：

| 探针 | 未打补丁 | 已打补丁 |
| :--- | :--- | :--- |
| `probe_editor_border.py`（120×40，看 editor 宽度的长横线） | editor 宽 紫 2 / 灰 4 ⇒ 失败 | editor 宽 紫 6 / 灰 0 ⇒ 通过 |
| `probe_dock_rows.py`（140×40） | 状态行之后还有 1 行空壳占位 ⇒ 失败 | 屏幕最后一行即主状态行 ⇒ 通过 |

`probe_dock_rows.py` 可选 `--send-prompt "…"` 真发一次提问，用来验证 `showLastPrompt`（回显行）开关；
不带该参数时全程离线、不调用模型。

**C3. 体检是什么**

`scripts/verify_plugin_ts.mjs` 用 **pi 自带的 jiti 加载器**真实 `import` 目标文件（等价于 pi 启动时的加载路径），
再实例化欢迎页组件渲染一次，断言：① TypeScript 语法与依赖解析可加载；② 每一行可见宽度自洽（中文全角不错位）；
③ 渲染结果命中期望中文标记。任一项失败，补丁引擎立即原子回滚。

## 常见避坑点与故障排查

| 现象 | 原因 | 处置 |
| :--- | :--- | :--- |
| 运行 `pi` 报 `SyntaxError` | 某条翻译含未转义引号 | 引擎的 `node --check` 会拦截并原子回滚；检查 `i18n/*.json` 引号转义，必要时 `bash scripts/apply_patch.sh --restore` |
| 「未检测到已安装的 pi」 | 当前 Shell 未加载全局 Node bin（fnm / nvm / mise） | 先 `which pi` 确认；或显式指定 `python3 scripts/patch_engine.py --apply --pkg-dir "/path/to/@earendil-works/pi-coding-agent"` |
| 版本不在适配清单、打补丁被拒 | 上游已发版但未更新 `SUPPORTED_VERSIONS` | 走维护线 A2；`--force` 仅限应急并需人工复核 dry-run 结果 |
| `/` 面板插件简介变回英文 | ① 插件改了措辞；② 软链被清理或指向异常；③ 刚升级插件未重载；④ 该命令是内置命令或提示词模板（不在插件汉化范围） | ① 跑 `--check` 同步 `en` / `zh`；② `install_plugin_i18n.sh --status` 后重跑安装脚本（幂等）；③ 会话内执行 `/reload`；④ 属正常现象，不处理 |
| 重复打补丁是否会污染基底 | 不会 | 引擎始终以 `.zh-backup` 干净原件为源；已存在备份时绝不重新覆盖 |
| 插件简介汉化会影响模型请求或插件行为吗 | 不会 | 仅改写补全面板展示用的 `description` 字符串，不触碰命令名、参数、工具定义与请求 payload；卸载后立即恢复原样 |
| 欢迎页汉化在插件升级后变回英文 | 插件升级重写了 `welcome.ts`，补丁被覆盖 | C 线属补丁式汉化，重跑 `bash scripts/apply_plugin_ui.sh` 即可幂等重打；先跑 `--check` 看有无漂移 |
| `--check` 报「未命中（上游可能改了措辞）」 | 上游改了文案或重构了表达式 | 按 C1 更新 `i18n/plugin-ui.json` 的 `en`/`zh` 后重跑 `--check`；`--allow-missing` 仅限应急且需人工复核 |
| 欢迎页中文串位 / 行宽错乱 | 中文全角宽度未被正确参与布局计算 | C3 体检会断言行宽自洽并自动回滚；若仍异常，先 `--restore` 再排查对应条目 |
| 从别处拷贝的 pi-zh 里没有 `.zh-backup` | 插件目录被重装或换机，备份不在版本控制内 | 正常：以当前官方文件为新基底重新备份即可，不影响幂等性 |

## 红线清单（违反即返工）

| 红线类别 | 违规案例 | 正确做法 |
| :--- | :--- | :--- |
| 命令名汉化 | `name: "compact"` 改为 `name: "压缩"` | 保留 `name: "compact"`，仅替换 `description` |
| 污染代码标识符 | 变量 `defaultProjectTrust` 被替换为 `defaultProject信任` | 单词替换必须用正则限定在引号字面量内匹配 |
| 覆盖干净基底 | 重复打补丁时覆盖了原有的 `.zh-backup` | 已存在备份时以备份为读取源，绝不重新备份 |
| 破坏版本号 | 把 `pi --version` 改为 `pi-zh 1.0` | 严格保留官方原始版本（如 `0.85.1`） |
| 改写插件源码 | 直接编辑 `node_modules` 中插件的 `description` | 仅允许「运行时覆盖 + `i18n/plugins.json` 字典映射」 |
| 越界翻译 | 翻译插件 `registerTool` 的工具描述或 skill 描述 | 工具描述会进模型请求 payload，一律不碰 |
| 插件渲染文案裸替换 | 用 `raw` 模式替换 `Tips` 这类短词，误伤同名标识符 | 短词一律用 `literal` 模式锁定引号；`raw` 仅用于自带上下文的模板片段 |
| C 线越权改逻辑 | 未授权就调整布局宽度、重写函数体或导出签名；或把行为改动混进 `replacements` | 文案改动只能进 `replacements`；行为改动只能进 `code_patches`，且必须带 `id`/`reason`/`authorized_on` 与回退分支；布局类改动（如 `dock-trim-*`）同样只能以「用户逐条授权 + 探针回归」的方式入字典 |

## 完成定义（DoD，一次合格交付的全部验收项）

```bash
cd /Users/jnq/Dev/Private/pi-zh

python3 tests/test_patch.py            # ① CLI 汉化单元测试与红线隔离测试
python3 tests/test_plugin_i18n.py      # ① 插件字典契约与扫描器测试
node tests/test_plugin_i18n.mjs        # ① 运行时覆盖扩展端到端契约测试
python3 tests/test_plugin_ui.py        # ① 插件 UI 汉化：字典契约 / 幂等 / 干净基底 / 未命中拦截 / 行为补丁授权校验
bash scripts/apply_patch.sh            # ② 补丁应用无报错（含 node --check 语法校验）
bash scripts/apply_plugin_ui.sh        # ② 插件 UI 补丁应用无报错（含 jiti 加载与渲染行宽体检）
bash scripts/smoke_test.sh             # ③ 五项冒烟全部通过
bash scripts/apply_patch.sh --restore              # ④ 还原可用：pi --help 恢复英文
bash scripts/install_plugin_i18n.sh --uninstall    # ④ 插件简介汉化可卸载：简介恢复英文
bash scripts/apply_plugin_ui.sh --restore          # ④ 插件 UI 汉化可还原：欢迎页恢复英文
python3 scripts/probe_editor_border.py             # ⑤ 行为补丁回归：editor 边框跟随思考层级色（紫 ≥4 且多于灰）
python3 scripts/probe_dock_rows.py                 # ⑤ 行为补丁回归：状态行占满 footer 槽位（屏幕最后一行即状态行）
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
  - `plugin-ui.json` — 插件 UI 补丁（欢迎页文案 `replacements` + 用户授权行为补丁 `code_patches`）
- **执行脚本（`scripts/`）**
  - `apply_patch.sh` — 一键应用 / 状态 / 还原 / dry-run 入口（A 线）
  - `patch_engine.py` — 补丁引擎（安全匹配、备份管理、`node --check` 校验、`SUPPORTED_VERSIONS`）
  - `install_plugin_i18n.sh` — 插件简介汉化：安装 / 状态 / 卸载（B 线）
  - `scan_plugin_commands.py` — 插件命令扫描与翻译漂移检查
  - `apply_plugin_ui.sh` — 插件 UI 汉化入口：应用 / 检查 / 状态 / 还原（C 线）
  - `patch_plugin_ui.py` — 插件渲染文案补丁引擎（未命中拦截、干净基底、失败回滚）
  - `verify_plugin_ts.mjs` — 插件 TS 体检器（jiti 真实加载 + 渲染行宽断言）
  - `probe_editor_border.py` — 行为补丁探针（pty 真启 pi，统计 thinking 紫边框 vs 244 灰边框）
  - `probe_dock_rows.py` — dock 行数探针（pty 解码最终帧，断言状态行占满 footer 槽位、无重复、无回显行）
  - `smoke_test.sh` — 五项冒烟测试
- **测试（`tests/`）**
  - `test_patch.py`、`test_plugin_i18n.py`、`test_plugin_i18n.mjs`、`test_plugin_ui.py`
- **文档**
  - `SOP.md` — 升级与维护标准操作手册（详细分步流程）
  - `AGENTS.md` — AI 维护契约、红线清单与完成定义
  - `00_状态.md` — 时空胶囊状态卡（当前基线 / 翻译条目规模 / 下一步）
  - `extensions/plugin-i18n.ts` — 插件简介运行时覆盖扩展
