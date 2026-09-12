# AGENTS.md — AI 维护契约与规范

本文档是 AI 代理（以及人类协作者）维护本仓库的核心契约。任何协助维护此项目的 AI 必须通读并严格遵守本规约。

---

## 维护原则

1. **单一职责**：本项目只做 CLI/TUI 界面与命令注释汉化，不触碰模型请求 Payload、上下文管理、RPC/CBOR 协议及业务逻辑。
2. **命令原名绝对锁定**：命令名称（`name`）与命令行参数（flags）是用户交互与自动化脚本的硬契约，**严禁汉化为中文**。仅汉化说明（`description`）与参数占位提示（`argumentHint`）。
3. **单一事实来源**：所有的翻译事实必须维护在 `i18n/*.json` 中，脚本中不得硬编码临时补丁文本。
4. **版本跟随**：官方发布新版后，以升级官方包为先导，更新 `patch_engine.py` 中的适配版本号并增量补齐未翻译条目。
5. **插件命令简介零侵入**：第三方插件的斜杠命令简介（`registerCommand` 的 `description`）一律走「运行时覆盖 + `i18n/plugins.json` 字典映射」，严禁改写 `~/.pi/agent/npm/node_modules` 内的任何插件文件。
6. **插件渲染文案最小补丁**：插件用字面量直接渲染的 TUI 文案（如 `pi-powerline-footer` 的欢迎页）没有任何注册接口可拦截，只能走「精确字面量补丁 + 干净基底 `.zh-backup` + 写盘后强制体检 + 一键还原」（维护线 C）。文案补丁只允许命中字符串字面量与模板片段。
7. **行为补丁授权通道**：C 线原则上不改插件行为；确有必要时（当前 3 条：editor 边框跟随思考层级色、欢迎页空壳先行、dock 去空白占位行），必须走 `i18n/plugin-ui.json` 的 `code_patches`，且同时满足四条：① 用户逐条明确授权并记录 `authorized_on`；② 写明 `reason`（为什么必须改、依据是什么）；③ 保留原实现作为回退分支，不删原逻辑；④ 与文案共用同一套预检、jiti 体检与 `--restore`。未授权的逻辑改动一律视为红线违规。
8. **懒人包只分发「协同必需」**：`bundle/` 的内容由 `scripts/bundle_engine.py` 的白名单定义产生（`SETTINGS_WHITELIST` + `BUNDLE_FILES`），判据是「**非默认值 + 非冲突解决 = 不带**」；凭据、会话数据、模型层配置、个人 skill / Agent / 注入词永不进包。
9. **导出单向**：维护者本机 `~/.pi/agent` 是 SSOT，`bundle/` 是派生物；**永不从仓库反向覆盖本机**。导出过程必须机器可核对、结果可复现，且产物不得含本机绝对路径。
10. **安装预检先于写盘**：冲突默认拒绝（退出码 2）并列出差异，需显式 `--force-settings` / `--force-files`（覆盖前自动备份）；只改白名单字段，幂等、可精确回滚，并保护用户的手工改动。

---

## 红线清单

任何一次改动，若触犯以下任一红线，必须立即回滚并重新设计：

| 红线分类 | 违规案例 | 正确做法 |
| :--- | :--- | :--- |
| **命令名汉化** | 把 `name: "compact"` 替换为 `name: "压缩"` | 保留 `name: "compact"`，仅替换 `description: "手动压缩会话上下文"` |
| **污染代码标识符** | 误把变量 `defaultProjectTrust` 替换为 `defaultProject信任` | 单独单词必须通过正则限定在引号 `(["'`])` 包裹内进行字面量匹配 |
| **覆盖干净基底** | 重复打补丁时覆盖了原有的 `.zh-backup` | 若已存在 `.zh-backup`，绝不可重新覆盖，必须以备份为读取源 |
| **破坏版本号** | 将 `pi --version` 改为 `pi-zh 1.0` | 严格保留官方原始版本（如 `0.85.1`） |
| **改写插件命令简介** | 直接编辑 `node_modules` 里的插件 `description` | 命令简介汉化只允许运行时覆盖（B 线），插件升级不得导致汉化失效 |
| **C 线越权改逻辑** | 未授权就调整布局宽度、重写函数体或导出签名；或把行为改动混进 `replacements` | 文案改动只能进 `replacements`；行为改动只能进 `code_patches`，且必须带 `id` / `reason` / `authorized_on` 与回退分支；布局类改动（如 `dock-trim-*`）同样只能以「用户逐条授权 + 探针回归」入字典 |
| **C 线裸单词替换** | 用 `raw` 模式替换 `Tips` 这种短词 | 短词一律用 `literal` 模式锁定在引号内；`raw` 模式必须自带足够上下文 |
| **越界翻译** | 把插件 `registerTool` 的工具描述或 skill 描述也译了 | 工具描述会进模型请求 payload，按单一职责红线一律不碰 |
| **懒人包夹带个人上下文** | 把 `auth.json` / `sessions/` / `models.json` / `trust.json` / 个人 skill / `APPEND_SYSTEM.md` 导进 `bundle/` | 只提取 `SETTINGS_WHITELIST` 与 `BUNDLE_FILES`；结构性排除项列入 `manifest.json` 的 `skip` 段并写明原因 |
| **导出物含本机绝对路径** | 自研扩展里写死 `/Users/jnq/...`；或把本机目录结构写进清单 | 路径一律相对 `$PI_AGENT_DIR`；导出前引擎会扫描绝对路径，命中即拒 |
| **反向覆盖本机** | 从 `bundle/` 往 `~/.pi/agent/` 做「同步」 | 导出单向：本机是 SSOT；修改本机只能由人在本机进行，再重新导出 |

---

## 完成定义 (Definition of Done)

只有满足以下全部验收项，一次针对 `pi-zh` 的维护或升级才被判定为合格交付：

1. `python3 tests/test_patch.py`、`python3 tests/test_plugin_i18n.py`、`node tests/test_plugin_i18n.mjs`、`python3 tests/test_plugin_ui.py`、`python3 tests/test_bundle.py` 单元测试全部通过。
2. `bash scripts/apply_patch.sh` 与 `bash scripts/apply_plugin_ui.sh` 执行无报错，补丁成功应用（引擎自带的 `node --check` / jiti 校验通过，无 `SyntaxError`）；`bash scripts/check_bundle.sh` 报告 `bundle/` 与维护者本机无漂移。
3. `bash scripts/smoke_test.sh` 五个 TEST 全部通过：
   - `pi --version` 正常输出官方版本；
   - `pi --help` 正常展示中文说明与中文参数；
   - 插件简介字典与已装插件无新增 / 漂移 / 残留差异；
   - 插件简介运行时覆盖扩展的端到端契约测试通过；
   - 插件 UI 汉化（C 线）字典无漂移，且欢迎页组件可加载、渲染行宽自洽。
4. 一键还原可用：`bash scripts/apply_patch.sh --restore` 能还原官方原版（`pi --help` 恢复英文），`bash scripts/install_plugin_i18n.sh --uninstall` 能卸载插件简介汉化，`bash scripts/apply_plugin_ui.sh --restore` 能还原插件 UI 英文，`bash scripts/install_bundle.sh --uninstall --keep-packages` 能精确回滚扩展环境（配置字段恢复原值、本包文件删除或还原）。
5. 行为补丁（`code_patches`）可回归验证：
   - `python3 scripts/probe_editor_border.py` 判定生效（editor 宽度 ≥100 列的紫色 thinking 边框行 ≥4 且多于同宽度灰行；基线：未打补丁 紫 2 / 灰 4，已打补丁 紫 6 / 灰 0）；
   - `python3 scripts/probe_dock_rows.py` 判定生效（屏幕最后一行即主状态行、无重复渲染、无回显行；`--restore` 后同一探针应判定回退：状态行之后仍有 1 行空壳占位）。
6. 代码与配置中无敏感凭据、个人路径或测试脏文件残留。
