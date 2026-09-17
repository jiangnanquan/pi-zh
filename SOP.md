# SOP.md — 升级与维护标准操作手册

本手册定义 `pi-zh` 在日常使用、官方新版发布后的升级适配以及故障排查的标准操作规程。

---

## 一、 日常使用规程

### 1. 应用补丁

```bash
# 自动定位当前环境中的全局 pi 并应用汉化
bash scripts/apply_patch.sh
```

### 2. 状态查询

```bash
bash scripts/apply_patch.sh --status
```

### 3. 一键还原

```bash
# 还原为官方英文原版并清理 .zh-backup 备份
bash scripts/apply_patch.sh --restore
```

### 4. 插件简介汉化（日常维护）

```bash
bash scripts/install_plugin_i18n.sh            # 安装/修复：软链扩展与字典到 ~/.pi/agent
bash scripts/install_plugin_i18n.sh --status   # 状态：软链健康度 + 字典覆盖数 + 与已装插件的差异
bash scripts/install_plugin_i18n.sh --uninstall # 卸载：插件简介立即恢复英文
```

汉化效果在 pi 会话内执行 `/reload` 后生效，无需重启进程。

### 5. 插件 UI 汉化（欢迎页等渲染文案）

```bash
bash scripts/apply_plugin_ui.sh              # 应用：备份基底 → 精确替换 → jiti 加载体检 → 渲染行宽断言
bash scripts/apply_plugin_ui.sh --check      # 漂移检测：字典是否全部命中（不写盘）
bash scripts/apply_plugin_ui.sh --status     # 状态：官方原版 / 已汉化（备份完好）
bash scripts/apply_plugin_ui.sh --restore    # 还原：欢迎页立即恢复英文
```

该汉化作用于插件**渲染期硬编码**的文案（如 `pi-powerline-footer` 的欢迎页 `welcome.ts`）——这类文案没有任何注册接口可拦截，
只能打精确字面量补丁；文案补丁只替换字符串与模板片段。重启 pi 后生效。

同一字典还承载**用户逐条授权的行为补丁**（`code_patches`），当前 3 条：

| `id` | 改了什么 |
| :--- | :--- |
| `editor-chrome-thinking-border` | powerline 重画的 editor 上下边框重新跟随 pi 的思考层级色（原先硬编码 ANSI 244 灰，盖掉了 `thinkingMax` 紫色） |
| `welcome-header-eager-shell` | 启动欢迎页先用空数据挂 header 立即上屏，取数完成后再换 header 重绘 |
| `dock-trim-primary-into-footer` | `placement=below` 时主状态行改由 footer 槽位渲染，消掉空壳 footer 白占的一行 |

行为补丁的验收需要真图形探针（pty 中真启一次 pi）：

```bash
python3 scripts/probe_editor_border.py       # 边框色：统计 editor 宽度的紫/灰长横线
python3 scripts/probe_dock_rows.py           # dock 行数：解码最终帧，断言状态行占满 footer 槽位
```

基线（退出码 0 = 生效，1 = 未生效）：

| 探针 | 未打补丁 | 已打补丁 |
| :--- | :--- | :--- |
| `probe_editor_border.py` | editor 宽 紫 2 / 灰 4 | editor 宽 紫 6 / 灰 0 |
| `probe_dock_rows.py` | 状态行之后还有 1 行空壳占位 | 屏幕最后一行即主状态行 |

> `probe_dock_rows.py` 的「回显行（↳ 上次输入）」判定跟随 pi 配置里的 `showLastPrompt`：为 `false` 时出现回显行即判失败；
> 为 `true` 时只提示。要离线复现「有回显行」的情形可加 `--send-prompt "…"`（会真实调用一次模型）。

### 6. 扩展环境懒人包（维护线 D 安装 / E 导出）

```bash
bash scripts/install_bundle.sh --dry-run      # 看安装计划（逐项列出配置 / 文件 / 扩展将做什么）
bash scripts/install_bundle.sh                # 安装：预检 → 备份 → 写白名单配置 → 落地扩展 → 装 packages（幂等）
bash scripts/install_bundle.sh --status       # 状态：配置 / 文件 / 扩展三项一致性
bash scripts/install_bundle.sh --uninstall    # 回滚：配置字段 + 文件 + 本包装过的扩展
bash scripts/install_bundle.sh --uninstall --keep-packages  # 只回滚配置与文件，保留扩展

bash scripts/export_bundle.sh                 # （维护者）本机 → bundle/ 单向导出（打印变更摘要）
bash scripts/check_bundle.sh                  # （维护者）漂移检测：本机改了但没导出？
```

懒人包的内容是一份声明（`bundle/manifest.json`）：扩展清单 + 协同必需配置 + 4 个自研扩展。
判据是「**非默认值 + 非冲突解决 = 不带**」——所以像 `powerline.placement`、`powerline.cost.currency`
这类纯偏好不在包内，随个人习惯。

`--uninstall` 是**精确回滚**：配置字段恢复安装前的值（原先没有的删除）、本包新建的文件删除、
被覆盖的文件从备份还原、只移除本包装过的扩展。若你在安装后手工改过某个字段或文件，
脚本会跳过它并提示，不会覆盖你的改动。

---

## 二、 官方发布新版本后的升级流程

当上游 `@earendil-works/pi-coding-agent` 发布新版本（例如 `0.86.0`）时，按以下流程进行增量适配：

### 步骤 1：确认并更新本地环境的官方包

```bash
npm update -g @earendil-works/pi-coding-agent
pi --version

# 遗留基底检查：升级后这里应为空。
# 若残留旧版 .zh-backup，必须先删掉再打补丁（否则引擎拿旧版文件当基底，写出新旧混杂的文件）。
PI_PKG=$(python3 -c "import sys; sys.path.insert(0,'scripts'); from patch_engine import locate_pi_package; print(locate_pi_package())")
find "$PI_PKG/dist" -name "*.zh-backup"
```

> 不建议给 pi 配自动升级（cron / launchd 定时 `pi update --all`）：升级会整体替换包目录，使 A 线汉化全部失效，
> 并使 C / F 线插件补丁的 `source_version` 失配。启动时的升级通知（已汉化）就是提醒入口，由人决定升级时机。

### 步骤 2：更新引擎支持版本

在 `scripts/patch_engine.py` 的 `SUPPORTED_VERSIONS` 数组中追加新版本号：

```python
SUPPORTED_VERSIONS = ["0.85.1", "0.86.0"]
```

### 步骤 3：执行 Dry-run 检测命中率

```bash
python3 scripts/patch_engine.py --dry-run
```

检查控制台输出的替换数量与未命中项。如果官方新增了命令或快捷键，可在 `i18n/commands.json` 或 `i18n/keybindings.json` 中增补词条；
启动升级通知（「新版本可用」/「插件包可更新」横幅）的文案在 `i18n/ui.json` 的 `exact_literals`。

### 步骤 4：全量应用与冒烟验收

```bash
bash scripts/apply_patch.sh
```

确认五项冒烟（版本输出、中文帮助、插件字典一致性、插件简介运行时覆盖、插件 UI 汉化）全部通过。

---

## 三、 插件升级/新增插件后的增量流程

插件（`pi-subagents`、`pi-powerline-footer` 等）升级后会重写 `node_modules` 下的文件，但因为汉化走运行时覆盖，**不会失效**；只有当插件改动了简介文案或新增命令时，才需要增量维护字典：

### 步骤 1：查看漂移

```bash
python3 scripts/scan_plugin_commands.py --check
```

输出分三类：

| 类型 | 含义 | 处置 |
| :--- | :--- | :--- |
| 新增未翻译 | 插件新增了命令 | 在 `i18n/plugins.json` 中补 `en`/`zh` |
| 原文漂移 | 插件改了简介措辞 | 同步 `en`（否则该命令回退英文显示），校对 `zh` |
| 字典残留 | 插件删了命令 | 从字典中删除对应条目 |

### 步骤 2：刷新基线（可选，仅改措辞时用）

```bash
python3 scripts/scan_plugin_commands.py --update-baseline
```

该命令只刷新 `en` 原文并把新命令登记为 `zh` 空串（空串自动跳过、保持英文），已译的 `zh` 不会被覆盖。

### 步骤 3：补齐翻译并验收

```bash
python3 tests/test_plugin_i18n.py    # 字典契约与扫描器测试
node tests/test_plugin_i18n.mjs      # 运行时覆盖端到端测试
bash scripts/smoke_test.sh           # 全量冒烟（含插件项）
```

---

## 四、 插件 UI 升级后的增量流程（维护线 C）

`pi-powerline-footer` 这类插件升级会重写整个包目录，**补丁式汉化会被官方文件覆盖**（连同 `.zh-backup` 一起消失），
但重打是幂等的、成本极低：

### 步骤 1：漂移检测

```bash
bash scripts/apply_plugin_ui.sh --check
```

- 全部命中：直接进入步骤 3；
- 报「未命中」：输出会逐条列出上游已改动的原文，进入步骤 2。

### 步骤 2：人工核对并更新字典

编辑 `i18n/plugin-ui.json`：

| 情况 | 处置 |
| :--- | :--- |
| 上游改了措辞 | 把对应条目的 `en` 同步为新措辞，并重新校对 `zh` |
| 上游删了该文案 | 从 `replacements` 中删除该条目 |
| 上游新增了文案 | 追加条目：短词用 `literal` 模式，带上下文的模板片段用 `raw` 模式 |

### 步骤 3：重打补丁并验收

```bash
bash scripts/apply_plugin_ui.sh      # 重新备份基线 → 应用 → jiti 加载体检 → 渲染行宽断言
python3 tests/test_plugin_ui.py      # 单测：幂等 / 干净基底 / 未命中拦截 / 行为补丁授权
python3 scripts/probe_editor_border.py    # 行为补丁回归：边框是否仍跟随思考层级色
python3 scripts/probe_dock_rows.py        # 行为补丁回归：状态行是否仍占满 footer 槽位（无空白占位行）
bash scripts/smoke_test.sh           # 全量冒烟（含 C 线项）
```

> 行为补丁（`code_patches`）比文案脆弱：它锚定的是插件实现代码。上游一旦重构该段，`--check` 会报未命中，
> 此时不要用 `--allow-missing` 绕过——应人工核对新版实现，重新给出 `from`，并确保新写法仍保留原实现作为回退分支
> （`editor-chrome-*` 保留灰色回退；`dock-trim-*` 在 `placement != below` 时保留原空壳行为）。

体检失败时引擎会自动从备份回滚，插件始终停留在可用状态。

---

## 五、 扩展环境懒人包（维护线 D 安装 / E 导出）

### 场景 1：在新机器上装一整套协同环境

1. 克隆仓库，确认 `pi` 已安装（`which pi` / `pi --version`）；
2. 问清意图：**只要汉化**（走一~四节）还是 **汉化 + 扩展环境**；
3. 先看计划：`bash scripts/install_bundle.sh --dry-run`；
4. 计划中出现「冲突」时**停下问人**：手工合并后重跑，还是用 `--force-settings` / `--force-files` 覆盖（覆盖前自动备份）；
5. 执行：`bash scripts/install_bundle.sh` —— 再依次执行 A / B / C 三条汉化线；
6. 验收：`bash scripts/install_bundle.sh --status` + `bash scripts/smoke_test.sh`；
7. 报告：装了什么、跳过什么（及原因）、如何卸载。

### 场景 2：改了自己的扩展 / 协同配置（维护者）

1. 在本机改完并实测生效；
2. `bash scripts/export_bundle.sh` —— 白名单提取 + 绝对路径校验，打印变更摘要；
3. `bash scripts/check_bundle.sh` 确认无漂移；
4. 把 `bundle/manifest.json` 与 `bundle/files/` 一起提交。

### 场景 3：排查「装了扩展但不显示」

```bash
bash scripts/install_bundle.sh --status     # 逐项对比：哪个配置字段 / 文件 / 扩展不一致
bash scripts/install_bundle.sh              # 幂等重跑即可补齐（已一致项自动跳过）
```

常见原因：只拷了扩展文件没写 `powerline.customItems` / `layout`（状态段须在此注册才会显示）；
或 `pi-powerline-footer` 未安装（自研扩展会退化为 pi 内置 footer 的扩展状态行）。

---

## 六、 插件功能补丁（维护线 F）

> 定位：C 线改的是「给人看的界面文案」，F 线改的是「给模型看的插件行为 / 工具返回」。
> 两者共用同一套引擎（`patch_plugin_ui.py`），只是字典不同（`--dict i18n/plugin-logic.json`）。

### 场景 1：日常检查与应用（幂等）

```bash
python3 scripts/patch_plugin_ui.py --dict i18n/plugin-logic.json --check    # 漂移检测（不写盘）
python3 scripts/patch_plugin_ui.py --dict i18n/plugin-logic.json --status   # 当前状态
python3 scripts/patch_plugin_ui.py --dict i18n/plugin-logic.json --apply    # 应用（体检失败自动回滚）
python3 scripts/patch_plugin_ui.py --dict i18n/plugin-logic.json --restore  # 一键还原官方原版
```

应用后需在 pi 会话内 `/reload`（或重启）才会加载新代码。

### 场景 2：上游插件升级后补丁失配

`--check` 报「行为补丁 xxx 未命中（上游改了该段实现）」时：

1. 逐字节复制上游新片段（**必须含 tab 缩进**），并用 `count()` 确认唯一命中；
2. 更新 `i18n/plugin-logic.json` 的 `from` / `to` 与 `source_version`；
3. 重跑 `--check` → `--apply`，写盘后 jiti 体检会断言 `verify_expect` 源码标记；
4. 严格模式（默认）在任何一条未命中时**拒绝写盘**，不会留下半成品。

### 场景 3：行为回归验证（新增/修改补丁后必做）

补丁的作用点是「模型看到的文本」，验收要直接用 pi 自带 jiti 加载补丁后的模块，构造样例 state/op 逐条断言。
至少覆盖三条路径：结算动作 + 有残留（应触发）、结算动作 + 无残留（不应触发）、非结算动作（不应触发）。

### 场景 4：排查「模型又开始漏结算」（F1 生效判定）

1. `--status` 确认补丁在位；2. 确认会话已 `/reload`；
3. 若仍漏结算：属**已知边界**——本补丁只在 todo 工具被调用时提醒，模型在未调用 todo 的回合里结束工作不会触发；
   这种情况应改 F 线设计（如回合末注入消息），**不得**直接改成「自动改状态」（会误杀跨轮合法任务）。

---

## 七、 常见问题与排查指南

### 1. 运行 `pi` 提示语法错误 (SyntaxError)
* **原因**：可能某条翻译中包含了未转义的单双引号。
* **处置**：引擎自带的 `node --check` 会在应用时拦截此类错误并自动回滚。若发生意外，执行 `bash scripts/apply_patch.sh --restore` 即可立即恢复原样。检查 `i18n/*.json` 中是否有非法字符。

### 2. 执行 `apply_patch.sh` 提示未检测到已安装的 `pi`
* **原因**：当前 Shell 路径未加载全局 Node.js bin 目录（例如使用了 fnm、nvm 或 mise）。
* **处置**：先在终端中执行 `which pi` 确认可执行文件存在；或者显式指定路径：
  ```bash
  python3 scripts/patch_engine.py --apply --pkg-dir "/path/to/@earendil-works/pi-coding-agent"
  ```

### 3. `/` 补全面板里插件简介又变回英文
* **可能原因与处置**：
  1. 插件改了简介措辞 → `python3 scripts/scan_plugin_commands.py --check` 会报「原文漂移」，按提示同步 `en`/`zh`；
  2. 软链被清理或指向异常 → `bash scripts/install_plugin_i18n.sh --status` 查看，再跑一次安装脚本（幂等）；
  3. 刚升级完插件、尚未重载 → 在会话内执行 `/reload`；
  4. 该命令是**内置命令或提示词模板**（标签为 `[t]` 等），不在插件汉化范围内。

### 4. 插件简介汉化会影响模型请求或插件行为吗
* **不会**。扩展只改写补全面板展示用的 `description` 字符串，不触碰命令名、参数、工具定义与请求 payload；卸载后立即恢复原样。

### 5. 欢迎页在插件升级后变回英文
* **原因**：插件升级重写了 `welcome.ts`，补丁被官方文件覆盖（C 线属补丁式汉化，这是预期行为）。
* **处置**：先 `bash scripts/apply_plugin_ui.sh --check` 看有无漂移，再 `bash scripts/apply_plugin_ui.sh` 幂等重打；有漂移时按第四节步骤 2 更新字典。

### 6. `--check` 报「未命中（上游可能改了措辞）」
* **原因**：插件改了文案措辞或重构了模板表达式，字典的 `en` 锚点已失效。
* **处置**：按第四节步骤 2 更新 `i18n/plugin-ui.json`。`--allow-missing` 只是应急逃生舱（未命中条目保持英文），不应作为常规流程。

### 7. editor 边框又变回浅灰了
* **原因**：插件升级重写了 `index.ts`，行为补丁被官方文件覆盖（或上游重构导致锚点失效）。
* **处置**：`bash scripts/apply_plugin_ui.sh --check` 看未命中项 → 按第四节步骤 2 更新 `code_patches` → 重打补丁 → 跑探针复验。

### 8. 输入框下方多出一行空白 / 多出「↳ 上次输入」回显行
* **原因（空白行）**：powerline 为了拿 pi 的 `footerData` 注册了一个空壳 footer（`render(): [""]`），
  而 pi 的 fullscreen dock 给 footer 槽位 `minSize: 1` 保底，于是空壳也占一行。`dock-trim-primary-into-footer`
  补丁已让 `placement=below` 时主状态行改由该槽位渲染。
* **处置**：先 `bash scripts/apply_plugin_ui.sh --status` 确认补丁在位；不在位就 `bash scripts/apply_plugin_ui.sh` 重打，
  再用 `python3 scripts/probe_dock_rows.py` 验收。若换了 `placement`（`/powerline placement above`），补丁会退回原空壳行为。
* **回显行**：`settings.json` 的 `showLastPrompt`（默认 `true`）控制「↳ 上次输入」回显行；置 `false` 即关闭。
  验证：`python3 scripts/probe_dock_rows.py --send-prompt "…"`（会真实调用一次模型）。

### 9. C 线汉化是否会把插件改坏
* **不会**。补丁只命中字符串字面量与模板片段，写盘后强制体检（jiti 真实加载 + 渲染行宽断言），任一项失败立即原子回滚；
  体检依赖 pi 自带的 jiti，若命令报「未检测到 node」而跳过体检，应按 `--skip-verify` 的风险处理：仅限离线单测使用。

### 10. 装懒人包时被拒（退出码 2）并列出冲突
* **原因**：本机已有不同的配置值或同名文件——默认不覆盖（防止弄丢你已有的偏好与自研扩展）。
* **处置**：先 `bash scripts/install_bundle.sh --dry-run` 看差异；手工合并后重跑（幂等），
  或确认要覆盖时加 `--force-settings` / `--force-files`（覆盖前会把原文件备份到 `bundle-backup-<时间戳>/`）。

### 11. 卸载后扩展包仍在
* **原因**：用了 `--keep-packages`，或该包在安装前就已存在（不属本包管理范围）。
* **处置**：单独移除 `pi remove <spec>`；查看本包装过哪些包：状态指针 `.pi-zh-bundle-state.json` 的 `packages_installed`。

### 12. 启动时的升级通知（新版本 / 插件包可更新）变回英文
* **原因**：上游改了通知文案或渲染表达式，`i18n/ui.json` 中的 `exact_literals` 锚点失配（A 线属补丁式汉化，提示被官方文件覆盖也属预期）。
* **处置**：对照新版原文更新 `i18n/ui.json` 的 6 条通知文案（标题 / 正文 / `Changelog:` 行 / `Packages:` 表头），再 `bash scripts/apply_patch.sh` 幂等重打。
* **注意**：含冒号的短串（如 `Changelog:`）必须带引号锁定为字面量，否则会误伤 `collapseChangelog: ` 这类属性名（`node --check` 会拦截回滚）。

### 13. 给 pi 配了自动升级（cron / launchd 定时 `pi update --all`）会怎样
* **会同时坏掉四条线**：
  1. A 线：升级整体替换包目录，汉化全部失效，需重新走第二节流程；
  2. C / F 线：插件与插件补丁的 `source_version` 失配，严格模式拒绝写盘，需人工重新锚定；
  3. 会话一致性：后台升级时机不可控，正在运行的会话会与磁盘代码不一致。
* **处置**：去掉定时任务，改为靠启动时的升级通知提醒（已汉化）＋人工决定的节奏；
  确需半自动化时也只做「检查 + 提醒」（如 `pi --version` 对比 `https://pi.dev/api/latest-version`），不要自动写盘。
