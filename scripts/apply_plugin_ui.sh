#!/usr/bin/env bash
# pi-zh — 插件 UI 汉化一键入口（维护线 C）
#
# 与 A 线 apply_patch.sh（pi 本体 dist bundle）互相独立：
#   C 线只处理插件「渲染期硬编码文案」，逐条精确字面量替换，留 .zh-backup 干净基底。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}   pi-zh — 插件 UI 汉化（维护线 C：欢迎页等渲染文案）  ${NC}"
echo -e "${CYAN}======================================================${NC}"

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[错误] 未检测到 python3，请先安装 Python 3。${NC}"
    exit 1
fi

MODE="apply"
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --restore) MODE="restore"; EXTRA_ARGS+=("--restore") ;;
        --status)  MODE="status";  EXTRA_ARGS+=("--status") ;;
        --check)   MODE="check";   EXTRA_ARGS+=("--check") ;;
        --dry-run) MODE="dry-run"; EXTRA_ARGS+=("--dry-run") ;;
        *) EXTRA_ARGS+=("$arg") ;;
    esac
done

case "$MODE" in
    restore)
        echo -e "${YELLOW}>>> 正在还原插件官方原版...${NC}"
        python3 "$SCRIPT_DIR/patch_plugin_ui.py" ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
        echo -e "${GREEN}>>> 还原完成，欢迎页恢复英文。${NC}"
        ;;
    status|check|dry-run)
        python3 "$SCRIPT_DIR/patch_plugin_ui.py" ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
        ;;
    *)
        echo -e "${CYAN}>>> 正在应用插件 UI 汉化（含 jiti 加载与渲染行宽体检）...${NC}"
        python3 "$SCRIPT_DIR/patch_plugin_ui.py" --apply ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
        echo -e "\n${GREEN}>>> 完成。重启 pi 或执行 /reload 即可看到中文欢迎页。${NC}"
        echo -e "${GREEN}>>> 还原：bash scripts/apply_plugin_ui.sh --restore${NC}"
        ;;
esac
