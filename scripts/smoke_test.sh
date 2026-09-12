#!/usr/bin/env bash
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}[TEST 1/5] 校验 pi --version (版本严格跟随官方)...${NC}"
VERSION_OUTPUT=$(pi --version)
echo "输出版本: $VERSION_OUTPUT"
if [ -z "$VERSION_OUTPUT" ]; then
    echo -e "${RED}[失败] pi --version 未返回有效版本号！${NC}"
    exit 1
fi
echo -e "${GREEN}[通过] 版本号正常输出。${NC}"

echo -e "\n${CYAN}[TEST 2/5] 校验 pi --help (中文帮助与参数说明)...${NC}"
HELP_OUTPUT=$(pi --help)
if echo "$HELP_OUTPUT" | grep -q "AI 终端编程助手"; then
    echo -e "${GREEN}[通过] 检测到中文帮助标头。${NC}"
else
    echo -e "${RED}[失败] 未在 pi --help 中检测到汉化文本！${NC}"
    exit 1
fi

if echo "$HELP_OUTPUT" | grep -q "用法:"; then
    echo -e "${GREEN}[通过] 检测到中文用法说明 (用法:)。${NC}"
else
    echo -e "${RED}[失败] 未在 pi --help 中检测到汉化用法 (用法:)！${NC}"
    exit 1
fi

if echo "$HELP_OUTPUT" | grep -q "选项参数:"; then
    echo -e "${GREEN}[通过] 检测到中文选项参数 (选项参数:)。${NC}"
else
    echo -e "${RED}[失败] 未在 pi --help 中检测到汉化选项参数 (选项参数:)！${NC}"
    exit 1
fi

echo -e "\n${CYAN}[TEST 3/5] 校验插件简介字典与已装插件一致...${NC}"
if python3 "$(dirname "${BASH_SOURCE[0]}")/scan_plugin_commands.py" --check; then
    echo -e "${GREEN}[通过] 字典基线无新增 / 漂移 / 残留。${NC}"
else
    echo -e "${RED}[失败] 插件简介字典与已装插件不一致，请按提示补齐。${NC}"
    exit 1
fi

echo -e "\n${CYAN}[TEST 4/5] 校验插件简介运行时覆盖扩展的端到端行为...${NC}"
if node "$(dirname "${BASH_SOURCE[0]}")/../tests/test_plugin_i18n.mjs" >/tmp/pi-zh-plugin-test.log 2>&1; then
    echo -e "${GREEN}[通过] 运行时覆盖扩展行为符合契约（9 项断言）。${NC}"
else
    echo -e "${RED}[失败] 插件简介汉化扩展测试未通过，日志：/tmp/pi-zh-plugin-test.log${NC}"
    tail -20 /tmp/pi-zh-plugin-test.log
    exit 1
fi

echo -e "\n${CYAN}[TEST 5/5] 校验插件 UI 汉化（维护线 C：欢迎页渲染文案）...${NC}"
PLUGIN_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}/npm/node_modules/pi-powerline-footer"
if [ -d "$PLUGIN_DIR" ]; then
    if python3 "$(dirname "${BASH_SOURCE[0]}")/patch_plugin_ui.py" --check >/tmp/pi-zh-plugin-ui-check.log 2>&1; then
        echo -e "${GREEN}[通过] 插件 UI 字典与已装插件一致（无漂移）。${NC}"
    else
        echo -e "${RED}[失败] 插件 UI 字典漂移，日志：/tmp/pi-zh-plugin-ui-check.log${NC}"
        tail -20 /tmp/pi-zh-plugin-ui-check.log
        exit 1
    fi

    RENDER_EXPECT=()
    if [ -f "$PLUGIN_DIR/welcome.ts.zh-backup" ]; then
        RENDER_EXPECT=(--expect "欢迎回来" --expect "最近会话")
    fi
    if node "$(dirname "${BASH_SOURCE[0]}")/verify_plugin_ts.mjs" --target "$PLUGIN_DIR/welcome.ts" --render-width 110 ${RENDER_EXPECT+"${RENDER_EXPECT[@]}"} >/tmp/pi-zh-plugin-ui-render.log 2>&1; then
        echo -e "${GREEN}[通过] 欢迎页组件可加载且渲染行宽自洽。${NC}"
    else
        echo -e "${RED}[失败] 欢迎页渲染体检未通过，日志：/tmp/pi-zh-plugin-ui-render.log${NC}"
        tail -20 /tmp/pi-zh-plugin-ui-render.log
        exit 1
    fi
else
    echo -e "${YELLOW}[跳过] 未安装 pi-powerline-footer，无需校验插件 UI 汉化。${NC}"
fi

echo -e "\n${GREEN}[OK] 冒烟测试全部通过！命令原名 100% 保持英文，界面与说明汉化成功！${NC}"
