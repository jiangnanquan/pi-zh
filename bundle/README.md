# pi 扩展协同环境（懒人包）

> 一套**装完就能协同工作**的 pi 扩展组合 + 汉化入口。
> 不是复制某个人的个人配置——只带扩展清单、协同配置、自研扩展和汉化。

## 这是什么

pi 的扩展各自都很强，但放在一起会互相抢资源、抢屏幕位置：

- `pi-cc-extensions` 启动时清空 header，`pi-powerline-footer` 异步把欢迎页挂回去，中间有一段空白；
- 4 个自研状态段（上下文条 / TPS / 缓存命中率 / DeepSeek 余额）不在 `powerline.customItems` 里注册就不会显示；
- 内建段与自研段口径重复，同一条信息会在状态栏出现两次。

本包就是这些「摩擦点」的**已验证解**：一份声明（`manifest.json`），把扩展清单与让它们不打架的配置固化下来。

**本包不含**：任何凭据、会话数据、个人 skill / Agent / 注入词、模型偏好、主题偏好。

## 怎么安装

### 交给 AI（推荐）

把这个仓库的地址发给你的 AI Agent，让它读 `../SKILL.md` 并执行 **D 线（扩展环境安装）**。

它会先探测你的环境、问你「只要汉化」还是「汉化 + 扩展环境」，然后调用 `../scripts/install_bundle.sh` 完成安装——冲突时会停下来问你，不会覆盖你已有的配置。

### 手动安装

```bash
git clone <本仓库地址> pi-zh && cd pi-zh

# 1) 先看计划（不写盘）：会列出每个字段/文件/扩展将要做什么
bash scripts/install_bundle.sh --dry-run

# 2) 安装（幂等，可重复执行）
bash scripts/install_bundle.sh

# 3) 汉化（A/B/C 三条线，详见 ../SKILL.md）
bash scripts/apply_patch.sh                 # pi 本体界面
bash scripts/install_plugin_i18n.sh         # 插件简介
bash scripts/apply_plugin_ui.sh             # 插件渲染文案（欢迎页）

# 4) 验收
bash scripts/install_bundle.sh --status     # 配置 / 文件 / 扩展三项一致性
bash scripts/smoke_test.sh                  # 五项冒烟
```

如果目标机器上已有同名配置或文件，脚本会**拒绝覆盖并列出冲突**（退出码 2）。确认要覆盖时：

```bash
bash scripts/install_bundle.sh --force-settings --force-files   # 覆盖前自动备份
```

## 装了什么

| 类别 | 内容 | 为什么必须带 |
| :--- | :--- | :--- |
| 扩展 | `manifest.json` 的 `packages`（7 个） | 扩展清单本体 |
| 配置 | `quietStartup: true` | 不带则 cc 清空 header、foot 异步填充，重现约 660ms 启动空窗 |
| 配置 | `tuiMode: "fullscreen"` | CC 扩展 fullscreen 交互（单击展开 / hover 高亮 / 回到底部）的前提 |
| 配置 | `powerline.customItems` + `layout` | 不带则自研扩展装了也不显示——状态段须在此注册 |
| 配置 | `powerline.disabledSegments` | 关掉内建 `context_pct` / `cache_read`，避免与自研段重复显示 |
| 文件 | `claude-code-style.json` | 不带则 cc 绘制自己的 logo header，与欢迎页再次冲突 |
| 文件 | 4 个自研扩展 | `cache-hit.ts` / `context-bar.ts` / `ds-balance.ts` / `tps-status.ts` |
| 汉化 | A / B / C 线 | 简体中文界面（随仓库的分发，不在本包内） |

**判据**：`非默认值 + 非冲突解决 = 不带`。所以像 `powerline.placement`（状态栏位置）、`powerline.cost.currency`（货币单位）这类纯偏好不在包内，随你自己的习惯。

**可选增强**：C 线的 `dock-trim-primary-into-footer` 行为补丁只在 `powerline.placement: "below"`（状态栏在输入框下方）时生效——它会把主状态行挪进 footer 槽位，消掉输入框下方空壳 footer 白占的一行。本包不带 `placement`（纯偏好，pi 默认 `above`），想要这个效果就自己设：

```jsonc
// ~/.pi/agent/settings.json
"powerline": { "placement": "below" },
"showLastPrompt": false   // 可选：再关掉「↳ 上次输入」回显行（powerline 读取，默认 true）
```

## 不装什么（结构性排除）

`manifest.json` 的 `skip` 段列了全部排除项及原因，包括：`auth.json`（凭据）、`sessions/` / `missions/`（数据）、`npm/`（由 `packages` 清单重建）、`models.json`（模型层）、`trust.json`（含本机路径）、`extensions/herdr-agent-state.ts` 与 `extensions/otty-integration.ts`（外部工具生成，目标机器会自行生成）等。

## 外部依赖

| 对象 | 依赖 | 缺失时行为 |
| :--- | :--- | :--- |
| `npm:pi-deepseek-search` | DeepSeek 凭据 | 仅联网搜索工具不可用，不影响启动 |
| `extensions/ds-balance.ts` | DeepSeek 凭据 | 扩展自守卫：非 DeepSeek provider 时不请求、不渲染该段 |

非 DeepSeek 用户可放心安装，或先跳过这两个包（`--skip-packages` 后自行挑选）。

## 卸载

```bash
bash scripts/install_bundle.sh --uninstall                # 完整回滚（含本包安装的扩展）
bash scripts/install_bundle.sh --uninstall --keep-packages # 只回滚配置与文件，保留扩展
```

回滚是**精确**的：配置字段恢复为安装前的值（原先没有的则删除），本包新建的文件删除、被覆盖的文件从备份还原，只移除本包安装过的扩展。若你在安装后手工改过某个字段或文件，脚本会**跳过它并提示**，不会覆盖你的改动。

安装前的完整备份保留在 `~/.pi/agent/bundle-backup-<时间戳>/`，可人工复查。

## 给维护者

本目录是**派生物**：真身（SSOT）是维护者本机的 `~/.pi/agent`。导出单向，绝不反向覆盖。

```bash
bash scripts/export_bundle.sh      # 从本机重新导出（打印变更摘要）
bash scripts/check_bundle.sh       # 漂移检测：本机改了但没导出？
```

新增或修改自研扩展后，先跑 `export_bundle.sh`，再跑 `check_bundle.sh` 确认一致，并把 `manifest.json` 与 `bundle/files/` 一起提交。
