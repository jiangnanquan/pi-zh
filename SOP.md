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

确认两个测试（版本输出、中文帮助）全部通过。

---

## 三、 常见问题与排查指南

### 1. 运行 `pi` 提示语法错误 (SyntaxError)
* **原因**：可能某条翻译中包含了未转义的单双引号。
* **处置**：引擎自带的 `node --check` 会在应用时拦截此类错误并自动回滚。若发生意外，执行 `bash scripts/apply_patch.sh --restore` 即可立即恢复原样。检查 `i18n/*.json` 中是否有非法字符。

### 2. 执行 `apply_patch.sh` 提示未检测到已安装的 `pi`
* **原因**：当前 Shell 路径未加载全局 Node.js bin 目录（例如使用了 fnm、nvm 或 mise）。
* **处置**：先在终端中执行 `which pi` 确认可执行文件存在；或者显式指定路径：
  ```bash
  python3 scripts/patch_engine.py --apply --pkg-dir "/path/to/@earendil-works/pi-coding-agent"
  ```
