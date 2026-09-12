#!/usr/bin/env bash
# pi-zh — 扩展环境懒人包：安装 / 状态 / 卸载（维护线 D）
#
# 载体是 bundle/manifest.json 的声明：扩展清单 + 协同配置 + 4 个自研扩展。
# 汉化本体不在此包内，随 pi-zh 仓库的 A/B/C 线脚本分发。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

usage() {
    cat <<EOF
用法: bash scripts/install_bundle.sh [选项]

  （无选项）    安装：预检 → 备份 → 写白名单配置 → 落地扩展 → 安装扩展包（幂等）
  --dry-run     只看安装计划，不写盘
  --status      查看安装状态与一致性（配置 / 文件 / 扩展三项）
  --uninstall   回滚最近一次安装（配置字段 + 文件；扩展包默认一并移除）
  --keep-packages   卸载时保留扩展包，只回滚配置与文件
  --force-settings  允许覆盖与包内不一致的已有配置字段（默认拒绝并停下）
  --force-files     允许覆盖与包内不一致的已有文件（覆盖前自动备份）
  --skip-packages   跳过扩展包安装，只写配置与文件
  --init            允许在 settings.json 不存在的目录新建配置
  --restore-from DIR  状态指针丢失时，指定备份目录（含 state.json）用于回滚
  --agent-dir DIR   pi agent 目录（默认 ~/.pi/agent，或环境变量 PI_CODING_AGENT_DIR）

环境变量:
  PI_CODING_AGENT_DIR  pi 官方支持的配置目录覆盖（默认 ~/.pi/agent）
  PI_BIN               pi 可执行文件路径（默认从 PATH 查找）
EOF
}

MODE="install"
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
        --uninstall)   MODE="uninstall"; EXTRA_ARGS+=("--uninstall") ;;
        --status)      MODE="status";    EXTRA_ARGS+=("--status") ;;
        --dry-run)     MODE="dry-run";   EXTRA_ARGS+=("--dry-run") ;;
        *) EXTRA_ARGS+=("$arg") ;;
    esac
done

case "$MODE" in
    uninstall)
        echo -e "${CYAN}======================================================${NC}"
        echo -e "${CYAN}   pi-zh — 扩展环境懒人包卸载（维护线 D）              ${NC}"
        echo -e "${CYAN}======================================================${NC}"
        python3 "$SCRIPT_DIR/bundle_engine.py" --uninstall ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
        ;;
    status)
        python3 "$SCRIPT_DIR/bundle_engine.py" --status ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
        ;;
    dry-run)
        echo -e "${CYAN}======================================================${NC}"
        echo -e "${CYAN}   pi-zh — 扩展环境懒人包安装计划（dry-run）           ${NC}"
        echo -e "${CYAN}======================================================${NC}"
        python3 "$SCRIPT_DIR/bundle_engine.py" --install --dry-run ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"}
        ;;
    *)
        echo -e "${CYAN}======================================================${NC}"
        echo -e "${CYAN}   pi-zh — 扩展环境懒人包安装（维护线 D）              ${NC}"
        echo -e "${CYAN}======================================================${NC}"
        rc=0
        python3 "$SCRIPT_DIR/bundle_engine.py" --install ${EXTRA_ARGS+"${EXTRA_ARGS[@]}"} || rc=$?
        if [ "$rc" -eq 0 ]; then
            echo -e "\n${GREEN}>>> 安装完成。${NC}"
            echo -e "${GREEN}>>> 状态检查：bash scripts/install_bundle.sh --status${NC}"
            echo -e "${GREEN}>>> 回滚：    bash scripts/install_bundle.sh --uninstall${NC}"
        fi
        exit "$rc"
        ;;
esac
