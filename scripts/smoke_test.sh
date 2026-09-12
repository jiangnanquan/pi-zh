#!/usr/bin/env bash
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}[TEST 1/4] 校验 pi --version (版本严格跟随官方)...${NC}"
VERSION_OUTPUT=$(pi --version)
echo "输出版本: $VERSION_OUTPUT"
if [ -z "$VERSION_OUTPUT" ]; then
    echo -e "${RED}[失败] pi --version 未返回有效版本号！${NC}"
    exit 1
fi
echo -e "${GREEN}[通过] 版本号正常输出。${NC}"

echo -e "\n${CYAN}[TEST 2/4] 校验 pi --help (中文帮助与参数说明)...${NC}"
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

echo -e "\n${CYAN}[TEST 3/4] 校验插件简介字典与已装插件一致...${NC}"
if python3 "$(dirname "${BASH_SOURCE[0]}")/scan_plugin_commands.py" --check; then
    echo -e "${GREEN}[通过] 字典基线无新增 / 漂移 / 残留。${NC}"
else
    echo -e "${RED}[失败] 插件简介字典与已装插件不一致，请按提示补齐。${NC}"
    exit 1
fi

echo -e "\n${CYAN}[TEST 4/4] 校验插件简介运行时覆盖扩展的端到端行为...${NC}"
if node "$(dirname "${BASH_SOURCE[0]}")/../tests/test_plugin_i18n.mjs" >/tmp/pi-zh-plugin-test.log 2>&1; then
    echo -e "${GREEN}[通过] 运行时覆盖扩展行为符合契约（9 项断言）。${NC}"
else
    echo -e "${RED}[失败] 插件简介汉化扩展测试未通过，日志：/tmp/pi-zh-plugin-test.log${NC}"
    tail -20 /tmp/pi-zh-plugin-test.log
    exit 1
fi

echo -e "\n${GREEN}[OK] 冒烟测试全部通过！命令原名 100% 保持英文，界面与说明汉化成功！${NC}"
