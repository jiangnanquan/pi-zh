#!/usr/bin/env bash
# pi-zh — 扩展环境懒人包：漂移检测（维护线 E）
#
# 对比本机（SSOT）与仓库 bundle/（派生物），报出「本机改了但没导出」。
# 只读不写盘，可安全地放进巡检与冒烟流程。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}   pi-zh — 扩展环境懒人包漂移检测（维护线 E）          ${NC}"
echo -e "${CYAN}======================================================${NC}"

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[错误] 未检测到 python3，请先安装 Python 3。${NC}"
    exit 1
fi

exec python3 "$SCRIPT_DIR/bundle_engine.py" --check "$@"
