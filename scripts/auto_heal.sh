#!/usr/bin/env bash
# pi-zh — 全链路汉化与补丁自动自愈守卫
#
# 用途：
#   当用户或系统升级了 pi 插件（如 pi-powerline-footer、@juicesharp/rpiv-todo）
#   导致补丁被官方原版覆盖时，本脚本可秒级自动自愈，重新应用汉化与行为补丁，
#   并在补丁完全命中时通过 --auto-bump 自动对齐版本号。
#
# 用法：
#   bash scripts/auto_heal.sh            # 交互式检查并自愈
#   bash scripts/auto_heal.sh --silent   # 极速静默模式（用于 shell 包装器/hook）
#   bash scripts/auto_heal.sh --check    # 仅巡检状态不执行写盘
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SILENT=false
CHECK_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --silent|-q) SILENT=true ;;
        --check)     CHECK_ONLY=true ;;
    esac
done

log_info() {
    if [ "$SILENT" = false ]; then
        echo -e "\033[0;36m[pi-zh 自愈]\033[0m $1"
    fi
}

log_success() {
    if [ "$SILENT" = false ]; then
        echo -e "\033[0;32m[pi-zh 自愈]\033[0m $1"
    fi
}

log_warn() {
    if [ "$SILENT" = false ]; then
        echo -e "\033[1;33m[pi-zh 自愈]\033[0m $1"
    fi
}

log_error() {
    echo -e "\033[0;31m[pi-zh 自愈]\033[0m $1" >&2
}

AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"
MODULES_DIR="$AGENT_DIR/npm/node_modules"

FOOTER_BACKUP="$MODULES_DIR/pi-powerline-footer/welcome.ts.zh-backup"
TODO_BACKUP="$MODULES_DIR/@juicesharp/rpiv-todo/tool/response-envelope.ts.zh-backup"

NEEDS_HEAL=false

# 1. 检查 C 线（pi-powerline-footer 欢迎页）
if [ -d "$MODULES_DIR/pi-powerline-footer" ] && [ ! -f "$FOOTER_BACKUP" ]; then
    NEEDS_HEAL=true
    log_warn "检测到 pi-powerline-footer 欢迎页补丁缺失（可能已被升级覆盖）"
fi

# 2. 检查 F 线（@juicesharp/rpiv-todo 行为补丁）
if [ -d "$MODULES_DIR/@juicesharp/rpiv-todo" ] && [ ! -f "$TODO_BACKUP" ]; then
    NEEDS_HEAL=true
    log_warn "检测到 @juicesharp/rpiv-todo 行为补丁缺失（可能已被升级覆盖）"
fi

# 3. 检查 A 线（pi 本体）
CLI_STATUS=$(python3 "$SCRIPT_DIR/patch_engine.py" --status 2>/dev/null || true)
if echo "$CLI_STATUS" | grep -q "官方原版"; then
    NEEDS_HEAL=true
    log_warn "检测到 Pi 本体处于官方原版状态"
fi

if [ "$NEEDS_HEAL" = false ]; then
    log_info "全部组件均已处于汉化与补丁状态，无需自愈。"
    exit 0
fi

if [ "$CHECK_ONLY" = true ]; then
    log_warn "存在需要自愈的组件（--check 模式，未执行写盘）。"
    exit 1
fi

log_info "正在自动执行自愈补丁..."

# 执行 C 线自愈（带 auto-bump）
if [ -d "$MODULES_DIR/pi-powerline-footer" ] && [ ! -f "$FOOTER_BACKUP" ]; then
    if [ "$SILENT" = true ]; then
        python3 "$SCRIPT_DIR/patch_plugin_ui.py" --apply --auto-bump >/dev/null 2>&1 || {
            log_error "pi-powerline-footer 自愈失败，可能存在上游代码破坏性漂移，建议运行 bash scripts/apply_plugin_ui.sh --check 排查。"
        }
    else
        python3 "$SCRIPT_DIR/patch_plugin_ui.py" --apply --auto-bump
    fi
fi

# 执行 F 线自愈（带 auto-bump）
if [ -d "$MODULES_DIR/@juicesharp/rpiv-todo" ] && [ ! -f "$TODO_BACKUP" ]; then
    if [ "$SILENT" = true ]; then
        python3 "$SCRIPT_DIR/patch_plugin_ui.py" --dict "$ROOT_DIR/i18n/plugin-logic.json" --apply --auto-bump >/dev/null 2>&1 || {
            log_error "rpiv-todo 自愈失败，建议排查。"
        }
    else
        python3 "$SCRIPT_DIR/patch_plugin_ui.py" --dict "$ROOT_DIR/i18n/plugin-logic.json" --apply --auto-bump
    fi
fi

# 执行 A 线自愈
if echo "$CLI_STATUS" | grep -q "官方原版"; then
    if [ "$SILENT" = true ]; then
        python3 "$SCRIPT_DIR/patch_engine.py" --auto >/dev/null 2>&1 || {
            log_error "Pi 本体自动打补丁失败，请手动运行 python3 scripts/patch_engine.py --auto 查看原因。"
        }
    else
        python3 "$SCRIPT_DIR/patch_engine.py" --auto
    fi
fi

log_success "自愈流程执行完毕！已恢复汉化与补丁。"
