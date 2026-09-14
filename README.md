# pi-zh — Pi Agent CLI 简体中文汉化

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#)
[![Pi Version](https://img.shields.io/badge/Pi-0.85.1-green.svg)](#)

> 一个面向 [Pi Agent](https://github.com/badlogic/pi-mono)（`@earendil-works/pi-coding-agent`）的高品质 CLI/TUI 简体中文汉化补丁。
> **命令名称 100% 保持英文原文**，仅汉化命令注释、参数提示、设置菜单、状态栏与快捷键说明，绝不破坏键盘肌肉记忆与脚本自动化。
> 另附「扩展协同环境懒人包」：一份声明（扩展清单 + 协同必需配置 + 4 个自研扩展），让装好的扩展不打架。

---

## 核心设计理念

本项目延续并对齐 `agy-zh` 与 `opencode-zh` 的工业级汉化规范体系：

- **命令保持原文**：`/settings`、`/model`、`/compact`、`/tree` 等所有内置斜杠命令名称严格保留英文，仅汉化对应的功能描述（`description`）与参数提示（`argumentHint`）。
- **零破坏性与干净基底**：打补丁前自动保留干净的官方原件备份（`.zh-backup`），每次打补丁均基于原始原件执行，杜绝“补丁叠补丁”；支持一键秒级还原回官方原版。
- **语法安全沙箱**：每次补丁写入后，引擎自动使用 `node --check` 进行 JavaScript 语法树校验，校验未通过则立即原子回滚，绝不产生损坏的半成品文件。
- **版本严格跟随**：`pi --version` 严格显示上游官方版本号（当前基准 v0.85.1），不自造版本号。
- **插件简介零侵入**：第三方插件的命令简介汉化走「运行时覆盖 + 字典映射」，不写入任何插件文件，插件升级后无需重新打补丁。
- **插件渲染文案最小补丁**：插件渲染期硬编码的文案（如欢迎页）没有注册接口可拦截，只能打精确字面量补丁；补丁只动字符串与模板片段，配 `.zh-backup` 干净基底、jiti 加载体检与一键还原。
- **行为补丁走授权通道**：C 线原则上不改插件行为；例外（如让 powerline 的 editor 边框重新跟随 pi 的思考层级色）必须进 `code_patches`，带 `id`/`reason`/`authorized_on`、保留原实现作回退，并用 pty 探针回归验证。

---

## 快速开始

### 1. 一键应用汉化

在终端执行：

```bash
# 自动寻址全局已安装的 pi、创建安全备份、应用汉化并自动执行冒烟测试
bash scripts/apply_patch.sh
```

### 2. 检查汉化状态

```bash
bash scripts/apply_patch.sh --status
```

### 3. 一键还原官方英文原版

```bash
bash scripts/apply_patch.sh --restore
```

### 4. 插件简介汉化（第三方扩展，可选）

```bash
# 安装：把运行时覆盖扩展与翻译字典软链到 ~/.pi/agent（幂等，可重复执行）
bash scripts/install_plugin_i18n.sh

# 查看状态：软链是否就绪、字典覆盖了多少条、与已装插件是否有差异
bash scripts/install_plugin_i18n.sh --status

# 卸载：移除软链，插件简介立即恢复英文
bash scripts/install_plugin_i18n.sh --uninstall
```

安装后在 pi 会话内执行 `/reload`（或重启 pi）即可看到中文简介。

### 5. 插件 UI 汉化（欢迎页等渲染文案）

```bash
# 应用：备份干净基底 → 精确字面量替换 → jiti 加载体检 → 渲染行宽断言
bash scripts/apply_plugin_ui.sh

# 漂移检测：插件升级后看字典是否仍全部命中（不写盘）
bash scripts/apply_plugin_ui.sh --check

# 状态 / 还原
bash scripts/apply_plugin_ui.sh --status
bash scripts/apply_plugin_ui.sh --restore
```

覆盖 `pi-powerline-footer` 的启动欢迎页（`welcome.ts`）：提示语、已加载计数、最近会话与相对时间的文案。重启 pi 后生效。
同一条维护线还含**三条用户授权行为补丁**（均带 `id` / `reason` / `authorized_on` 与回退分支）：

1. `editor-chrome-thinking-border` —— powerline 重画的 editor 上下边框原本硬编码 ANSI 244 灰，盖掉了 pi 本体随
   思考层级变化的边框色（`max` → `#ff5fff` 紫）；改为优先继承 pi 注入的 `borderColor`，并保留灰色回退。
2. `welcome-header-eager-shell` —— 启动欢迎页先用空数据挂 header 立即上屏，取数完成后再换 header 重绘。
3. `dock-trim-primary-into-footer` —— `placement=below` 时主状态行改由 footer 槽位渲染，消掉 powerline 空壳
   footer 白占的那一行（pi 的 dock 给 footer 槽位 `minSize: 1` 保底）。

行为验收用真图形探针（pty 启动一次 pi，解码最终帧）：

```bash
python3 scripts/probe_editor_border.py   # 边框色：未打补丁 editor 宽 紫 2 / 灰 4；已打补丁 紫 6 / 灰 0
python3 scripts/probe_dock_rows.py       # dock 行数：未打补丁状态行后还有空壳占位行；已打补丁状态行即最后一行
```

### 6. 扩展协同环境懒人包（可选，新机器友好）

> **已在用 [`pi-team-setup`](https://github.com/jiangnanquan/pi-team-setup)？跳过本步。** 团队引导包内置的就是同一套扩展组合（包清单、`powerline` 注册、4 个自研扩展），两者高度同源，同时安装会互相覆盖 `powerline` 配置。分工是：**团队同事走 `pi-team-setup` 的 `SETUP.md`**（其中第 6 步会回来调本仓的 A/B/C 汉化线，不装本包），**自己攒环境才走本仓 D 线**。若已两边都装：先 `bash scripts/install_bundle.sh --status` 看清配置现状，再用 `--uninstall`（可加 `--keep-packages` 保留扩展包）退掉本包侧，团队侧用 `pi remove git:github.com/jiangnanquan/pi-team-setup@main`。

分发一套**装完就能协同工作**的扩展组合（不是复制个人配置）：扩展清单 + 协同必需配置 + 4 个自研扩展。
人类可读说明见 [`bundle/README.md`](bundle/README.md)。

```bash
# 先看计划（不写盘）：逐项列出配置 / 文件 / 扩展将做什么
bash scripts/install_bundle.sh --dry-run

# 安装（幂等，可重复执行；冲突时退出码 2 并列出差异，默认不覆盖你已有的配置）
bash scripts/install_bundle.sh

# 状态 / 回滚
bash scripts/install_bundle.sh --status
bash scripts/install_bundle.sh --uninstall                 # 含本包装过的扩展
bash scripts/install_bundle.sh --uninstall --keep-packages # 只回滚配置与文件
```

维护者侧（单向：本机是 SSOT，`bundle/` 是派生物）：

```bash
bash scripts/export_bundle.sh    # 从本机重新导出，打印变更摘要
bash scripts/check_bundle.sh     # 漂移检测：本机改了但没导出？
```

---

## 插件简介汉化（运行时覆盖）

第三方插件（`pi-subagents`、`pi-powerline-footer`、`pi-cc-extensions` 等）在 `/` 补全面板里展示的简介由插件自身的 `registerCommand(name, { description })` 决定，是纯英文且随插件升级频繁变化。

本项目**不修改任何插件源码**，而是用一个轻量扩展在运行时包一层补全器：

- 只在「`/` 开头且尚未输入空格」的命令名补全场景下，把候选项第二列的英文简介正文替换成中文；
- 命令名（`item.value`）、参数原名、来源标签 `[u:npm:xxx]` 全部原样保留；
- 仅在英文原文与 `i18n/plugins.json` 的 `en` 基线**逐字一致**时才替换 —— 因此绝不会误伤同名但不同来源的内置命令、提示词模板或 skill；插件改了措辞时只是回退成英文，不会翻错；
- 插件升级、重装、回滚都不影响汉化效果，无需重新打补丁。

翻译事实统一维护在 `i18n/plugins.json`（`source` / `en` / `zh` 三元组），插件升级后跑一次漂移检查即可低成本增量补齐：

```bash
python3 scripts/scan_plugin_commands.py --check            # 报告新增 / 原文漂移 / 字典残留
python3 scripts/scan_plugin_commands.py --update-baseline   # 刷新 en 原文基线（保留已译 zh）
```

---

## 插件 UI 汉化（渲染文案补丁）

有些插件文案在**渲染期硬编码**（`pi-powerline-footer` 的欢迎页 `welcome.ts` 就是典型），没有任何注册接口可供扩展拦截，
运行时覆盖无能为力，因此这条线改用“最小补丁”：

- 汉化条目全部维护在 `i18n/plugin-ui.json`，短词用 `literal` 模式（只命中引号内字面量），带上下文的模板片段用 `raw` 模式；
- 首次打补丁前留存官方原件 `welcome.ts.zh-backup`，重复应用均以备份为源，**永不补丁叠补丁**，随时 `--restore` 秒级回到英文；
- 上游改措辞时以“未命中”形式报漂移，默认拒绍写盘，不产生半成品汉化；
- 写盘后强制体检：`scripts/verify_plugin_ts.mjs` 用 **pi 自带的 jiti 加载器**真实加载插件源码，
  再实例化欢迎页组件渲染一次，断言行宽自洽（中文全角不错位）；失败立即原子回滚。

```bash
bash scripts/apply_plugin_ui.sh          # 应用或幂等重打
bash scripts/apply_plugin_ui.sh --check  # 插件升级后的漂移检测
python3 tests/test_plugin_ui.py          # 幂等 / 干净基底 / 未命中拦截 / 可还原 单测
```

---

## 目录结构

```text
pi-zh/
├── README.md                    # 本文件（项目介绍与快速开始）
├── AGENTS.md                    # AI 代理维护契约（红线清单与完成定义）
├── SOP.md                       # 升级与维护标准操作规程
├── LICENSE                      # MIT 开源协议
├── i18n/                        # 机器可读的精准中英翻译规则集
│   ├── commands.json            # 斜杠命令翻译表（name 锁原文，译注释/提示）
│   ├── keybindings.json         # 快捷键说明翻译表
│   ├── settings.json            # 交互设置菜单选项翻译表
│   ├── cli.json                 # CLI --help 参数与帮助说明
│   ├── ui.json                  # TUI 状态栏与交互短语
│   ├── plugins.json             # 第三方插件斜杠命令简介（source/en/zh 三元组）
│   └── plugin-ui.json           # 插件 UI 补丁（欢迎页文案 + 用户授权行为补丁）
├── extensions/
│   └── plugin-i18n.ts           # 插件简介汉化的运行时覆盖扩展
├── scripts/
│   ├── apply_patch.sh           # 一键应用/还原入口脚本（A 线：pi 本体）
│   ├── patch_engine.py          # 补丁执行引擎（安全匹配、备份管理、语法校验）
│   ├── install_plugin_i18n.sh   # 插件简介汉化：安装 / 状态 / 卸载（B 线）
│   ├── scan_plugin_commands.py  # 插件命令扫描与翻译漂移检查
│   ├── apply_plugin_ui.sh       # 插件 UI 汉化：应用 / 检查 / 状态 / 还原（C 线）
│   ├── patch_plugin_ui.py       # 插件 UI 补丁引擎（跨文件原子预检、未命中拦截、回滚）
│   ├── verify_plugin_ts.mjs     # 插件 TS 体检器（jiti 加载 + 渲染行宽断言）
│   ├── probe_editor_border.py   # 行为补丁探针（pty 真启 pi，统计紫/灰边框行）
│   ├── probe_dock_rows.py       # dock 行数探针（pty 解码最终帧，断言状态行占满 footer 槽位）
│   ├── export_bundle.sh         # 懒人包导出入口（E 线：本机 → bundle/，单向）
│   ├── check_bundle.sh          # 懒人包漂移检测（E 线：不写盘）
│   ├── install_bundle.sh        # 懒人包安装 / 状态 / 卸载入口（D 线）
│   ├── bundle_engine.py         # 懒人包引擎（白名单提取、预检、精确回滚）
│   └── smoke_test.sh            # 一键冒烟测试脚本（五项）
├── bundle/                      # 扩展环境声明（由 E 线从维护者本机导出的派生物）
│   ├── manifest.json            # 机器生成的清单：packages / settings / files / skip / dependencies
│   ├── README.md                # 使用者视角说明（依赖、手动安装、卸载）
│   └── files/                   # 随包分发的实体文件（claude-code-style.json + 4 个自研扩展）
└── tests/
    ├── test_patch.py            # CLI 汉化的单元测试与红线隔离测试
    ├── test_plugin_i18n.py      # 插件字典契约与扫描器测试
    ├── test_plugin_i18n.mjs     # 运行时覆盖扩展的端到端契约测试
    ├── test_plugin_ui.py        # 插件 UI 汉化：幂等、干净基底与还原测试
    └── test_bundle.py           # 懒人包：白名单提取、冲突拦截、幂等、精确回滚测试
```

---

## 红线清单（违反即坏，禁止违背）

| 规则项 | 规范要求 | 潜在后果 |
| :--- | :--- | :--- |
| **命令名 原文锁定** | `/compact`、`/model` 等命令名禁止改为中文 | 破坏用户输入肌肉记忆及自动化工作流 |
| **CLI Flags 原文锁定** | `--provider`、`--thinking` 等参数名禁止修改 | 导致外部脚本与命令行调用参数失效 |
| **标识符与变量隔离** | 单独单词必须限定在字符串引号字面量内匹配 | 避免误伤 `defaultProjectTrust` 等内部变量名 |
| **基底还原机制** | 每次打补丁必须以干净的 `.zh-backup` 为源基底 | 避免重复 patch 累加导致语法或逻辑错乱 |
| **插件命令简介只读** | 命令简介汉化走运行时覆盖，禁止改写 `node_modules` 内插件的 `description` | 避免插件升级/重装后失效，以及破坏插件完整性校验 |
| **渲染文案补丁限界** | 文案补丁只能进 `replacements`，禁止改布局宽度、函数逻辑与导出签名 | 保证汉化不改变插件行为，且能被 jiti 体检与一键还原兜住 |
| **行为补丁必须授权** | 行为改动只能进 `code_patches`，且必须带 `id`/`reason`/`authorized_on` 与回退分支 | 改动可审计、可回滚，上游重构时能被未命中检测及时暴露 |
| **C 线禁止裸单词替换** | 短词必须用 `literal` 模式锁定在引号内 | 避免 `Tips` / `Loaded` 这类短词误伤同名标识符 |
| **懒人包不夹带个人上下文** | 只提取白名单字段与声明文件；凭据、会话、个人 skill / Agent / 注入词永不进包 | 防止个人数据泄漏与环境污染 |
| **导出单向** | 永不从 `bundle/` 反向覆盖本机 `~/.pi/agent` | 避免派生物污染 SSOT |
| **安装先预检** | 冲突默认拒绝，覆盖必须显式 `--force-*` | 避免弄丢用户已有配置与自研扩展 |

---

## 适用版本

| 组件 | 版本 | 说明 |
| :--- | :--- | :--- |
| `@earendil-works/pi-coding-agent` | `v0.85.1` | 当前严格适配版本 |
| 运行环境 | Node.js 20+ / 22+ | 跨 macOS、Linux 与 Windows |

---

## 开源协议

本项目基于 [MIT](LICENSE) 协议开源。
感谢 [badlogic/pi-mono](https://github.com/badlogic/pi-mono) 团队打造的优秀 AI Agent 工具链。
