#!/usr/bin/env bash
# pi-zh — 扩展环境懒人包：导出（维护线 E）
#
# 方向：本机 ~/.pi/agent 是 SSOT，仓库 bundle/ 是派生物。导出单向，绝不反向覆盖本机。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}   pi-zh — 扩展环境懒人包导出（维护线 E）              ${NC}"
echo -e "${CYAN}======================================================${NC}"

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[错误] 未检测到 python3，请先安装 Python 3。${NC}"
    exit 1
fi

exec python3 "$SCRIPT_DIR/bundle_engine.py" --export "$@"
