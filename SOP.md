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

---

## 二、 官方发布新版本后的升级流程

当上游 `@earendil-works/pi-coding-agent` 发布新版本（例如 `0.86.0`）时，按以下流程进行增量适配：

### 步骤 1：确认并更新本地环境的官方包

```bash
npm update -g @earendil-works/pi-coding-agent
pi --version
```

### 步骤 2：更新引擎支持版本

在 `scripts/patch_engine.py` 的 `SUPPORTED_VERSIONS` 数组中追加新版本号：

```python
SUPPORTED_VERSIONS = ["0.85.1", "0.86.0"]
```

### 步骤 3：执行 Dry-run 检测命中率

```bash
python3 scripts/patch_engine.py --dry-run
```

检查控制台输出的替换数量与未命中项。如果官方新增了命令或快捷键，可在 `i18n/commands.json` 或 `i18n/keybindings.json` 中增补词条。

### 步骤 4：全量应用与冒烟验收

```bash
bash scripts/apply_patch.sh
```

确认四个测试（版本输出、中文帮助、插件字典一致性、插件简介运行时覆盖）全部通过。

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

## 四、 常见问题与排查指南

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
