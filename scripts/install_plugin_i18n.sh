#!/usr/bin/env bash
# pi-zh — 第三方插件简介汉化：安装 / 查看状态 / 卸载
#
# 只做一件事：把仓库里的「运行时覆盖扩展」与「翻译字典」软链到 pi 的 agent 目录，
# 不修改任何第三方插件源码，因此插件升级、重装都不影响汉化效果。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AGENT_DIR="${PI_AGENT_DIR:-$HOME/.pi/agent}"
EXT_SRC="$PROJECT_ROOT/extensions/plugin-i18n.ts"
DICT_SRC="$PROJECT_ROOT/i18n/plugins.json"
EXT_LINK="$AGENT_DIR/extensions/plugin-i18n.ts"
DICT_LINK="$AGENT_DIR/plugin-i18n/plugins.json"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

usage() {
    cat <<EOF
用法: bash scripts/install_plugin_i18n.sh [选项]

  （无选项）    安装汉化扩展与字典软链接（幂等）
  --status     查看当前安装状态与字典覆盖情况
  --uninstall  移除软链接，恢复插件简介英文原文
  --force      链接已被占用时强制替换（默认拒绝，防止误删用户文件）

环境变量:
  PI_AGENT_DIR  pi agent 目录，默认 ~/.pi/agent
EOF
}

link_state() { # $1 = 链接路径，$2 = 期望目标
    if [ -L "$1" ]; then
        local actual
        actual="$(readlink "$1")"
        if [ "$actual" = "$2" ]; then echo "ok"; else echo "stale"; fi
    elif [ -e "$1" ]; then
        echo "occupied"
    else
        echo "missing"
    fi
}

do_install() { # $1 = force
    local force="$1"

    if [ ! -f "$EXT_SRC" ] || [ ! -f "$DICT_SRC" ]; then
        echo -e "${RED}[错误] 仓库文件缺失：$EXT_SRC 或 $DICT_SRC${NC}"
        exit 1
    fi

    mkdir -p "$AGENT_DIR/extensions" "$(dirname "$DICT_LINK")"

    for pair in "$EXT_LINK|$EXT_SRC|扩展" "$DICT_LINK|$DICT_SRC|字典"; do
        IFS='|' read -r link target label <<<"$pair"
        case "$(link_state "$link" "$target")" in
            ok)
                echo -e "${GREEN}[OK] ${label}软链已就绪：$link${NC}"
                ;;
            stale|missing)
                rm -f "$link"
                ln -s "$target" "$link"
                echo -e "${GREEN}[OK] 已创建${label}软链：$link -> $target${NC}"
                ;;
            occupied)
                if [ "$force" != "true" ]; then
                    echo -e "${RED}[错误] $link 已存在且不是本项目软链，未做改动。${NC}"
                    echo -e "${YELLOW}        确认要替换请追加 --force${NC}"
                    exit 1
                fi
                rm -f "$link"
                ln -s "$target" "$link"
                echo -e "${YELLOW}[WARN] 已强制替换${label}软链：$link -> $target${NC}"
                ;;
        esac
    done

    echo -e "\n${CYAN}>>> 校验字典与已装插件的一致性...${NC}"
    python3 "$SCRIPT_DIR/scan_plugin_commands.py" --check || true

    echo -e "\n${GREEN}安装完成。重启 pi，或在会话内执行 /reload 即可看到中文简介。${NC}"
}

do_status() {
    echo -e "${CYAN}=== plugin-i18n 安装状态 ===${NC}"
    for pair in "$EXT_LINK|$EXT_SRC|扩展" "$DICT_LINK|$DICT_SRC|字典"; do
        IFS='|' read -r link target label <<<"$pair"
        case "$(link_state "$link" "$target")" in
            ok) echo -e "  ${label}: ${GREEN}已安装${NC} ($link)" ;;
            stale) echo -e "  ${label}: ${YELLOW}指向异常${NC} ($link -> $(readlink "$link"))" ;;
            occupied) echo -e "  ${label}: ${YELLOW}被非本项目文件占用${NC} ($link)" ;;
            missing) echo -e "  ${label}: ${RED}未安装${NC} ($link)" ;;
        esac
    done

    echo -e "\n${CYAN}=== 字典覆盖情况 ===${NC}"
    python3 - "$DICT_SRC" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
commands = data.get("commands", {})
done = sum(1 for e in commands.values() if (e.get("zh") or "").strip())
todo = [name for name, e in commands.items() if not (e.get("zh") or "").strip()]
print(f"  条目总数: {len(commands)}    已汉化: {done}    待汉化: {len(todo)}")
if todo:
    print("  待汉化命令: " + ", ".join(sorted(todo)))
PY

    echo -e "\n${CYAN}=== 与已装插件的差异 ===${NC}"
    python3 "$SCRIPT_DIR/scan_plugin_commands.py" --check || true
}

do_uninstall() {
    for pair in "$EXT_LINK|扩展" "$DICT_LINK|字典"; do
        IFS='|' read -r link label <<<"$pair"
        if [ -L "$link" ]; then
            rm -f "$link"
            echo -e "${GREEN}[OK] 已移除${label}软链：$link${NC}"
        elif [ -e "$link" ]; then
            echo -e "${YELLOW}[跳过] $link 不是软链，未做改动${NC}"
        else
            echo -e "${YELLOW}[跳过] ${label}软链不存在：$link${NC}"
        fi
    done
    echo -e "\n${GREEN}卸载完成。重启 pi，或在会话内执行 /reload 即恢复英文简介。${NC}"
}

case "${1:-install}" in
    --status) do_status ;;
    --uninstall) do_uninstall ;;
    --force) do_install true ;;
    -h|--help) usage ;;
    install|"") do_install false ;;
    *)
        echo -e "${RED}[错误] 未知参数：$1${NC}"
        usage
        exit 1
        ;;
esac
