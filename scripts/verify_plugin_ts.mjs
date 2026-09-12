#!/usr/bin/env node
/**
 * pi-zh — 插件 TypeScript 补丁健康校验器（维护线 C 的强制体检环节）
 *
 * 为什么需要它：`node --check` 只能校验 JavaScript，无法校验 TypeScript 插件源码；
 * 而插件的 TUI 文案又直接决定渲染行宽。本脚本用 **pi 自带的 jiti 加载器**真实 import
 * 目标文件，等价于 pi 启动时的加载路径，因此能一次性验证：
 *
 *   ① TypeScript 语法与 relative/bare 依赖解析均可加载（等价于插件能被 pi 装载）；
 *   ② 导出的欢迎页组件可实例化并渲染，且每一行的可见宽度自洽（中文全角、ANSI 混排不错位）；
 *   ③ 渲染结果命中期望的中文标记（汉化确实生效，而不是只改了源码没生效）。
 *
 * 用法：
 *   node scripts/verify_plugin_ts.mjs --target ~/.pi/agent/npm/node_modules/pi-powerline-footer/welcome.ts \
 *        --render-width 110 --expect 欢迎回来 --expect 最近会话
 *
 * 退出码：0 通过；1 失败（调用方据此回滚）。
 */

import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

const ANSI_RE = /\x1b\[[0-9;]*m/g;

function parseArgs(argv) {
	const args = { expect: [] };
	for (let i = 0; i < argv.length; i++) {
		const token = argv[i];
		if (!token.startsWith("--")) continue;
		const key = token.slice(2);
		const value = argv[i + 1];
		if (key === "expect") {
			args.expect.push(value);
			i++;
		} else {
			args[key] = value;
			i++;
		}
	}
	return args;
}

function fail(message) {
	console.error(`[verify] 失败：${message}`);
	process.exit(1);
}

const PI_PACKAGE_NAME = "@earendil-works/pi-coding-agent";

/** 判断目录是否为 pi 包根（兼容 pnpm / fnm / npm 各种链接布局） */
function isPiPackageRoot(dir) {
	try {
		const meta = JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf8"));
		return meta?.name === PI_PACKAGE_NAME;
	} catch {
		return false;
	}
}

/** 从任意入口文件出发，逐级向上寻找名为 pi-coding-agent 的包根 */
function ascendToPiPackage(startPath) {
	let dir = path.dirname(startPath);
	for (let i = 0; i < 8; i++) {
		if (isPiPackageRoot(dir)) return dir;
		const parent = path.dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return null;
}

/** 定位全局安装的 @earendil-works/pi-coding-agent 包目录 */
function locatePiPackage(explicit) {
	if (explicit) {
		const resolved = path.resolve(explicit);
		if (isPiPackageRoot(resolved)) return resolved;
		fail(`--pi-pkg 未指向 ${PI_PACKAGE_NAME} 包目录：${resolved}`);
	}

	const piBin = process.env.PI_BIN || "pi";
	let resolvedBin = "";
	try {
		resolvedBin = execFileSync("bash", ["-lc", `command -v ${piBin}`], { encoding: "utf8" }).trim();
	} catch {
		resolvedBin = "";
	}

	if (resolvedBin) {
		let real = resolvedBin;
		try {
			real = fs.realpathSync(resolvedBin);
		} catch {
			/* 保留原始路径继续尝试 */
		}
		const fromBin = ascendToPiPackage(real);
		if (fromBin) return fromBin;
	}

	// 退路：npm root -g
	try {
		const npmRoot = execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim();
		const candidate = path.join(npmRoot, ...PI_PACKAGE_NAME.split("/"));
		if (isPiPackageRoot(candidate)) return candidate;
	} catch {
		/* 忽略，继续报错 */
	}

	fail(`未检测到已安装的 ${PI_PACKAGE_NAME}（command -v ${piBin} → ${resolvedBin || "空"}），可用 --pi-pkg 显式指定`);
}

/**
 * 复刻 pi 运行时给扩展用的模块别名（见 pi 的 loader.js → getAliases）。
 * 插件源码 import 的是裸包名（@earendil-works/pi-coding-agent 等），
 * 这些包并不在 ~/.pi/agent/npm/node_modules 下，必须显式指向 pi 自带的副本。
 */
function buildAliases(piPkg, piRequire) {
	const resolveFromPi = (spec) => {
		try {
			return piRequire.resolve(spec);
		} catch {
			return null;
		}
	};
	const distIndex = path.join(piPkg, "dist", "index.js");
	const piTui = resolveFromPi("@earendil-works/pi-tui");
	const piAgentCore = resolveFromPi("@earendil-works/pi-agent-core");
	const piAiCompat = resolveFromPi("@earendil-works/pi-ai/compat") ?? resolveFromPi("@earendil-works/pi-ai");
	const piAiOauth = resolveFromPi("@earendil-works/pi-ai/oauth");
	const piAiProviders = resolveFromPi("@earendil-works/pi-ai/providers/all");
	const aliases = {
		"@earendil-works/pi-coding-agent": distIndex,
		"@mariozechner/pi-coding-agent": distIndex,
	};
	const optional = {
		"@earendil-works/pi-tui": piTui,
		"@mariozechner/pi-tui": piTui,
		"@earendil-works/pi-agent-core": piAgentCore,
		"@mariozechner/pi-agent-core": piAgentCore,
		"@earendil-works/pi-ai": piAiCompat,
		"@earendil-works/pi-ai/compat": piAiCompat,
		"@earendil-works/pi-ai/oauth": piAiOauth,
		"@earendil-works/pi-ai/providers/all": piAiProviders,
	};
	for (const [spec, entry] of Object.entries(optional)) {
		if (entry) aliases[spec] = entry;
	}
	return aliases;
}

async function main() {
	const args = parseArgs(process.argv.slice(2));
	const target = args.target;
	if (!target) fail("缺少 --target 参数");
	const targetPath = path.resolve(target.replace(/^~(?=\/)/, process.env.HOME ?? "~"));
	if (!fs.existsSync(targetPath)) fail(`目标文件不存在：${targetPath}`);

	const piPkg = locatePiPackage(args["pi-pkg"]);
	const loaderPath = path.join(piPkg, "dist", "core", "extensions", "loader.js");
	const require = createRequire(loaderPath);
	let createJiti;
	try {
		({ createJiti } = require("jiti"));
	} catch (error) {
		fail(`无法从 pi 加载 jiti：${error?.message ?? error}`);
	}

	const jiti = createJiti(loaderPath, {
		moduleCache: false,
		alias: buildAliases(piPkg, createRequire(path.join(piPkg, "package.json"))),
	});

	let tui = null;
	let module;
	try {
		tui = await jiti.import("@earendil-works/pi-tui", { default: false }).catch(() => null);
		module = await jiti.import(targetPath, { default: false });
	} catch (error) {
		fail(`jiti 加载失败（语法或依赖解析异常）：${error?.message ?? error}`);
	}
	if (tui && typeof tui.visibleWidth !== "function") {
		tui = tui.default && typeof tui.default.visibleWidth === "function" ? tui.default : null;
	}

	const exported = Object.keys(module ?? {});
	const renderWidth = args["render-width"] ? Number(args["render-width"]) : 0;
	const notes = [`导出 ${exported.length} 个符号`];

	/** 检查期望标记；scope 描述检查面（渲染输出 / 源码文本） */
	const assertExpect = (text, scope) => {
		if (args.expect.length === 0) return;
		const missing = args.expect.filter((marker) => !text.includes(marker));
		if (missing.length > 0) fail(`未命中期望标记（${scope}）：${missing.map((m) => JSON.stringify(m)).join(", ")}`);
		notes.push(`命中标记 ${args.expect.length}/${args.expect.length}（${scope}）`);
	};

	if (renderWidth > 0) {
		const ComponentClass = module?.WelcomeHeader ?? module?.WelcomeComponent;
		if (typeof ComponentClass === "function") {
			let component;
			try {
				component = new ComponentClass(
					"DeepSeek V4.1 Flash",
					"deepseek",
					[
						{ name: "pi-zh", timeAgo: "46m ago" },
						{ name: "jnq", timeAgo: "6h ago" },
					],
					{ contextFiles: 1, extensions: 15, skills: 0, promptTemplates: 3 },
					3700,
				);
			} catch (error) {
				fail(`组件实例化失败：${error?.message ?? error}`);
			}
			if (typeof component?.setCountdown === "function") component.setCountdown(30);

			let lines;
			try {
				lines = component.render(renderWidth);
			} catch (error) {
				fail(`组件渲染失败：${error?.message ?? error}`);
			}
			if (!Array.isArray(lines)) fail("组件的 render() 未返回字符串数组");

			const measure = tui?.visibleWidth ?? ((line) => String(line).replace(ANSI_RE, "").length);
			const widths = new Set();
			for (const line of lines) {
				const plain = String(line).replace(ANSI_RE, "");
				if (!plain.trim()) continue;
				widths.add(measure(line));
			}
			if (widths.size > 1) {
				fail(`渲染行宽不自洽：可见宽度出现 ${[...widths].join(", ")} 多种取值（中文全角或 ANSI 拼装疑似被破坏）`);
			}
			if (widths.size === 0) fail("渲染结果为空");

			const rendered = lines.map((line) => String(line).replace(ANSI_RE, "")).join("\n");
			for (const line of lines) console.log(`[render] ${line}`);

			notes.push(`渲染 ${lines.length} 行`);
			notes.push(`行宽自洽 ${[...widths][0]} 列`);
			assertExpect(rendered, "渲染输出");
		} else {
			notes.push("目标未导出欢迎页组件，跳过渲染检查");
			assertExpect(fs.readFileSync(targetPath, "utf8"), "源码文本");
		}
	} else {
		assertExpect(fs.readFileSync(targetPath, "utf8"), "源码文本");
	}

	console.log(`[verify] 已加载 ${path.basename(targetPath)}：${notes.join("，")}`);
}

main().catch((error) => fail(error?.stack ?? String(error)));
