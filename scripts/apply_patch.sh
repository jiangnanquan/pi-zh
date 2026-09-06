#!/usr/bin/env bash
# pi-zh 一键汉化与还原脚本
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}       pi-zh — Pi Agent CLI 简体中文汉化补丁          ${NC}"
echo -e "${CYAN}======================================================${NC}"

# 检查 Python3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[错误] 未检测到 python3，请先安装 Python 3。${NC}"
    exit 1
fi

# 检查 Node.js
if ! command -v node &>/dev/null; then
    echo -e "${RED}[错误] 未检测到 node 环境。${NC}"
    exit 1
fi

MODE="apply"
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --restore)
            MODE="restore"
            EXTRA_ARGS+=("--restore")
            ;;
        --status)
            MODE="status"
            EXTRA_ARGS+=("--status")
            ;;
        --dry-run)
            MODE="dry-run"
            EXTRA_ARGS+=("--dry-run")
            ;;
        --force)
            EXTRA_ARGS+=("--force")
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

if [ "$MODE" = "restore" ]; then
    echo -e "${YELLOW}>>> 正在还原官方原版...${NC}"
    python3 "$SCRIPT_DIR/patch_engine.py" ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
    echo -e "${GREEN}>>> 还原成功！已恢复官方原版。${NC}"
    exit 0
fi

if [ "$MODE" = "status" ]; then
    python3 "$SCRIPT_DIR/patch_engine.py" ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
    exit 0
fi

if [ "$MODE" = "dry-run" ]; then
    echo -e "${CYAN}>>> 正在进行 Dry-run 模拟替换检测...${NC}"
    python3 "$SCRIPT_DIR/patch_engine.py" ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
    exit 0
fi

echo -e "${CYAN}>>> 正在应用汉化补丁...${NC}"
python3 "$SCRIPT_DIR/patch_engine.py" --apply ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}

echo -e "\n${CYAN}>>> 正在执行冒烟测试...${NC}"
bash "$SCRIPT_DIR/smoke_test.sh"

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}       pi-zh 汉化成功完成！随时输入 pi 体验。         ${NC}"
echo -e "${GREEN}       随时可通过: bash scripts/apply_patch.sh --restore 恢复原版  ${NC}"
echo -e "${GREEN}======================================================${NC}"
