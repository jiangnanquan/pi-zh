# pi-zh — Pi Agent CLI 简体中文汉化

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#)
[![Pi Version](https://img.shields.io/badge/Pi-0.85.1-green.svg)](#)

> 一个面向 [Pi Agent](https://github.com/badlogic/pi-mono)（`@earendil-works/pi-coding-agent`）的高品质 CLI/TUI 简体中文汉化补丁。
> **命令名称 100% 保持英文原文**，仅汉化命令注释、参数提示、设置菜单、状态栏与快捷键说明，绝不破坏键盘肌肉记忆与脚本自动化。

---

## 核心设计理念

本项目延续并对齐 `agy-zh` 与 `opencode-zh` 的工业级汉化规范体系：

- **命令保持原文**：`/settings`、`/model`、`/compact`、`/tree` 等所有内置斜杠命令名称严格保留英文，仅汉化对应的功能描述（`description`）与参数提示（`argumentHint`）。
- **零破坏性与干净基底**：打补丁前自动保留干净的官方原件备份（`.zh-backup`），每次打补丁均基于原始原件执行，杜绝“补丁叠补丁”；支持一键秒级还原回官方原版。
- **语法安全沙箱**：每次补丁写入后，引擎自动使用 `node --check` 进行 JavaScript 语法树校验，校验未通过则立即原子回滚，绝不产生损坏的半成品文件。
- **版本严格跟随**：`pi --version` 严格显示上游官方版本号（当前基准 v0.85.1），不自造版本号。
- **插件零侵入**：第三方插件的简介汉化走「运行时覆盖 + 字典映射」，不写入任何插件文件，插件升级后无需重新打补丁。

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
│   └── plugins.json             # 第三方插件斜杠命令简介（source/en/zh 三元组）
├── extensions/
│   └── plugin-i18n.ts           # 插件简介汉化的运行时覆盖扩展
├── scripts/
│   ├── apply_patch.sh           # 一键应用/还原入口脚本
│   ├── patch_engine.py          # 补丁执行引擎（安全匹配、备份管理、语法校验）
│   ├── install_plugin_i18n.sh   # 插件简介汉化：安装 / 状态 / 卸载
│   ├── scan_plugin_commands.py  # 插件命令扫描与翻译漂移检查
│   └── smoke_test.sh            # 一键冒烟测试脚本
└── tests/
    ├── test_patch.py            # CLI 汉化的单元测试与红线隔离测试
    ├── test_plugin_i18n.py      # 插件字典契约与扫描器测试
    └── test_plugin_i18n.mjs     # 运行时覆盖扩展的端到端契约测试
```

---

## 红线清单（违反即坏，禁止违背）

| 规则项 | 规范要求 | 潜在后果 |
| :--- | :--- | :--- |
| **命令名 原文锁定** | `/compact`、`/model` 等命令名禁止改为中文 | 破坏用户输入肌肉记忆及自动化工作流 |
| **CLI Flags 原文锁定** | `--provider`、`--thinking` 等参数名禁止修改 | 导致外部脚本与命令行调用参数失效 |
| **标识符与变量隔离** | 单独单词必须限定在字符串引号字面量内匹配 | 避免误伤 `defaultProjectTrust` 等内部变量名 |
| **基底还原机制** | 每次打补丁必须以干净的 `.zh-backup` 为源基底 | 避免重复 patch 累加导致语法或逻辑错乱 |
| **插件源码只读** | 插件简介汉化走运行时覆盖，禁止改写 `node_modules` 内插件文件 | 避免插件升级/重装后被覆盖、以及破坏插件完整性校验 |

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
