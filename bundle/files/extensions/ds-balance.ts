/**
 * ds-balance — pi 底部状态栏显示 DeepSeek 账户余额（¥）与低余额变色提醒。
 *
 * 数据源：DeepSeek 官方 `GET https://api.deepseek.com/user/balance`
 * （官方唯一的账户端点；不提供 token 用量或消费历史 API）。
 * 密钥取自 pi 的 provider 认证解析（ctx.modelRegistry.getProviderAuth("deepseek")），
 * 回退环境变量 DEEPSEEK_API_KEY，因此不直接读取 auth.json。
 *
 * 显示形态：`¥1664.54`，余额向下越限时转 warning/error 色；
 * 上一次请求失败时保留旧值并追加 `~`。仅当活动 provider 为 deepseek
 * 且处于交互模式时请求；`pi -p` 等无头模式不发任何请求。
 *
 * 每次成功获取会追加 `{t, currency, total}` 到 pi-deepseek-balance-snapshots.jsonl
 * （与 npm 包 pi-deepseek-balance 同文件同格式，便于将来接续其消耗速率估算）。
 *
 * 配合 pi-powerline-footer 时在 settings.json 提升为 footer segment：
 *   "powerline": { "customItems": [
 *     { "id": "ds-balance", "statusKey": "ds-balance", "position": "right", "selfColorize": true } ] }
 *
 * 环境变量：
 *   PI_DEEPSEEK_BALANCE_CURRENCY    指定币种行（如 CNY / USD；默认按 CNY 优先的启发式选择）
 *   PI_DEEPSEEK_BALANCE_THRESHOLDS  `"20,5"` 余额阈值（警告,告急；某一档 0 即关闭该档）
 *   PI_CODING_AGENT_DIR             pi 配置目录（快照落盘位置，默认 ~/.pi/agent）
 *
 * 命令：`/ds-balance` 强制刷新并报告；`/ds-balance --json` 输出原始数据。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const STATUS_KEY = "ds-balance";
const BALANCE_URL = "https://api.deepseek.com/user/balance";
const THROTTLE_MS = 5 * 60_000; // 余额变化缓慢，5 分钟节流足够
const TIMEOUT_MS = 8_000;
const MAX_AUTH_FAILURES = 2; // 凭据被拒连续达到此次数后停止请求，直到模型重新选择

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR ?? join(homedir(), ".pi", "agent");
const SNAPSHOT_PATH = join(AGENT_DIR, "pi-deepseek-balance-snapshots.jsonl");

// ---------------------------------------------------------------------------
// 类型（最小依赖面，避免绑定可能变动的内部类型）
// ---------------------------------------------------------------------------

type CurrencyRow = {
	currency?: string;
	total_balance?: string;
	granted_balance?: string;
	topped_up_balance?: string;
};

type Balance = {
	is_available?: boolean;
	balance_infos?: CurrencyRow[];
};

type UiLike = {
	setStatus: (key: string, text?: string) => void;
	notify: (message: string, level?: "info" | "warning" | "error") => void;
	theme: { fg: (color: string, text: string) => string };
};

type CtxLike = {
	ui: UiLike;
	mode?: string;
	hasUI?: boolean;
	model?: { provider?: string };
	modelRegistry?: {
		getProviderAuth: (provider: string) => Promise<{ auth?: { apiKey?: string } } | undefined>;
	};
};

type Thresholds = { warn: number; urgent: number };

/** 密钥被拒（401/403），与网络/服务端错误区别对待 */
class AuthError extends Error {}

// ---------------------------------------------------------------------------
// 纯函数
// ---------------------------------------------------------------------------

/** 阈值解析：`"20,5"` → {warn:20, urgent:5}；0 表示关闭该档 */
function parseThresholds(raw: string | undefined): Thresholds {
	const parts = (raw ?? "20,5")
		.split(",")
		.map((s) => Number(s.trim()))
		.filter((n) => Number.isFinite(n) && n >= 0);
	return { warn: parts[0] ?? 20, urgent: parts[1] ?? 5 };
}

/**
 * 币种行选择：不取第一行 —— 零余额的 USD 行不应遮蔽正余额的 CNY 行。
 * 顺序：环境变量指定 → 首个正数 CNY 行 → 首个正数行 → 存在 CNY 行则取 CNY → 第一行。
 */
function pickRow(balance: Balance, override: string | undefined): CurrencyRow | null {
	const rows = (balance.balance_infos ?? []).filter((r) => r && typeof r.currency === "string");
	if (rows.length === 0) return null;

	const total = (r: CurrencyRow) => {
		const n = Number(r.total_balance);
		return Number.isFinite(n) ? n : Number.NEGATIVE_INFINITY;
	};
	const hasBalance = (r: CurrencyRow) => total(r) > 0;

	if (override) {
		const up = override.trim().toUpperCase();
		const exact = rows.find((r) => r.currency?.toUpperCase() === up);
		if (exact) return exact;
	}
	return (
		rows.find((r) => r.currency === "CNY" && hasBalance(r)) ??
		rows.find(hasBalance) ??
		rows.find((r) => r.currency === "CNY") ??
		rows[0]
	);
}

/** 金额文本保留两位小数；非数字原样返回（端点以字符串返回金额） */
function formatAmount(raw: string | undefined): string {
	const n = Number(raw);
	return Number.isFinite(n) ? n.toFixed(2) : (raw ?? "?");
}

function symbolFor(currency: string | undefined): string {
	return currency === "CNY" ? "¥" : currency === "USD" ? "$" : `${currency ?? ""} `;
}

/** 余额对应的主题色名：低于告急/警告阈值时降级配色 */
function colorFor(value: number, t: Thresholds): string {
	if (t.urgent > 0 && value < t.urgent) return "error";
	if (t.warn > 0 && value < t.warn) return "warning";
	return "accent";
}

function isInteractive(ctx: CtxLike): boolean {
	return ctx.mode === "tui" || ctx.hasUI === true;
}

/** 快照落盘（best-effort，绝不因磁盘问题影响状态栏） */
function appendSnapshot(row: CurrencyRow): void {
	try {
		const payload = {
			t: Date.now(),
			currency: row.currency,
			total: Number(formatAmount(row.total_balance)),
		};
		appendFileSync(SNAPSHOT_PATH, `${JSON.stringify(payload)}\n`);
	} catch {
		// 忽略：快照只服务于未来的速率估算
	}
}

// ---------------------------------------------------------------------------
// 扩展主体
// ---------------------------------------------------------------------------

export default function dsBalance(pi: ExtensionAPI): void {
	const env = process.env as Record<string, string | undefined>;
	const thresholds = parseThresholds(env["PI_DEEPSEEK_BALANCE_THRESHOLDS"]);
	const currencyOverride = env["PI_DEEPSEEK_BALANCE_CURRENCY"];

	let active = false;
	let row: CurrencyRow | null = null;
	let fetchedAt = 0;
	let stale = false;
	let authFailures = 0;
	let inFlight = false;
	let lastUi: UiLike | null = null;

	/** 渲染当前状态；无数据且未激活时清除 status */
	function render(ui: UiLike): void {
		if (!active) {
			ui.setStatus(STATUS_KEY, undefined);
			return;
		}
		if (authFailures >= MAX_AUTH_FAILURES) {
			ui.setStatus(STATUS_KEY, ui.theme.fg("error", "DS 密钥无效"));
			return;
		}
		if (!row) {
			ui.setStatus(STATUS_KEY, ui.theme.fg("dim", "DS …"));
			return;
		}
		const value = Number(formatAmount(row.total_balance));
		const text = `${symbolFor(row.currency)}${formatAmount(row.total_balance)}`;
		if (stale) {
			ui.setStatus(STATUS_KEY, ui.theme.fg("dim", `${text} ~`));
			return;
		}
		ui.setStatus(STATUS_KEY, ui.theme.fg(colorFor(value, thresholds), text));
	}

	/** 取密钥：pi 的 provider 认证解析优先，环境变量兜底 */
	async function apiKeyFor(ctx: CtxLike): Promise<string | undefined> {
		try {
			const resolved = await ctx.modelRegistry?.getProviderAuth("deepseek");
			const key = resolved?.auth?.apiKey;
			if (typeof key === "string" && key.length > 0) return key;
		} catch {
			// 解析失败时回退环境变量
		}
		return env["DEEPSEEK_API_KEY"];
	}

	async function fetchBalance(key: string): Promise<Balance> {
		const res = await fetch(BALANCE_URL, {
			headers: { Authorization: `Bearer ${key}`, Accept: "application/json" },
			signal: AbortSignal.timeout(TIMEOUT_MS),
		});
		if (res.status === 401 || res.status === 403) throw new AuthError();
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
		return (await res.json()) as Balance;
	}

	/** 刷新余额（force=true 跳过节流），失败时保留旧值并标记 stale */
	async function refresh(ctx: CtxLike, force: boolean): Promise<void> {
		if (!isInteractive(ctx) || !active || inFlight) return;
		if (authFailures >= MAX_AUTH_FAILURES) return;
		if (!force && Date.now() - fetchedAt < THROTTLE_MS) return;

		const key = await apiKeyFor(ctx);
		if (!key) {
			active = false;
			lastUi?.setStatus(STATUS_KEY, ctx.ui.theme.fg("dim", "DS 无密钥"));
			return;
		}

		inFlight = true;
		try {
			const balance = await fetchBalance(key);
			const picked = pickRow(balance, currencyOverride);
			if (picked) {
				row = picked;
				fetchedAt = Date.now();
				stale = false;
				authFailures = 0;
				appendSnapshot(picked);
			}
		} catch (err) {
			// 认证失败：计数后停用；其余错误（网络/超时/5xx）保留旧值并标记过期
			if (err instanceof AuthError) {
				authFailures += 1;
				if (authFailures >= MAX_AUTH_FAILURES) {
					ctx.ui.notify("DeepSeek 密钥被拒（401/403），余额显示已停止。请检查 /login 或 DEEPSEEK_API_KEY。", "error");
				}
			} else if (row) {
				stale = true;
			}
		} finally {
			inFlight = false;
			lastUi = ctx.ui;
			render(ctx.ui);
		}
	}

	pi.on("session_start", async (_event: unknown, ctxRaw: unknown) => {
		const ctx = ctxRaw as CtxLike;
		active = ctx.model?.provider === "deepseek";
		authFailures = 0;
		lastUi = ctx.ui;
		render(ctx.ui);
		if (active) await refresh(ctx, true);
	});

	pi.on("model_select", async (eventRaw: unknown, ctxRaw: unknown) => {
		const ctx = ctxRaw as CtxLike;
		const provider = (eventRaw as { model?: { provider?: string } })?.model?.provider ?? ctx.model?.provider;
		authFailures = 0;
		lastUi = ctx.ui;
		active = provider === "deepseek";
		if (!active) {
			row = null;
			stale = false;
			render(ctx.ui);
			return;
		}
		render(ctx.ui);
		await refresh(ctx, true);
	});

	pi.on("turn_end", async (_event: unknown, ctxRaw: unknown) => {
		await refresh(ctxRaw as CtxLike, false);
	});

	pi.on("session_shutdown", async () => {
		active = false;
		lastUi = null;
	});

	pi.registerCommand("ds-balance", {
		description: "刷新并报告 DeepSeek 账户余额（--json 输出原始数据）",
		handler: async (args: string, ctxRaw: unknown) => {
			const ctx = ctxRaw as CtxLike;
			lastUi = ctx.ui;
			active = ctx.model?.provider === "deepseek";
			authFailures = 0;
			if (!active) {
				ctx.ui.notify("当前活动 provider 不是 deepseek，余额查询已跳过。", "warning");
				return;
			}
			const key = await apiKeyFor(ctx);
			if (!key) {
				ctx.ui.notify("未找到 DeepSeek 密钥（/login 或 DEEPSEEK_API_KEY）。", "error");
				return;
			}
			try {
				const balance = await fetchBalance(key);
				const picked = pickRow(balance, currencyOverride);
				if (picked) {
					row = picked;
					fetchedAt = Date.now();
					stale = false;
					appendSnapshot(picked);
				}
				render(ctx.ui);

				if (args.trim() === "--json") {
					ctx.ui.notify(JSON.stringify(balance, null, 2), "info");
					return;
				}
				const lines = (balance.balance_infos ?? []).map(
					(r) =>
						`${symbolFor(r.currency)}${formatAmount(r.total_balance)}` +
						`（赠金 ${formatAmount(r.granted_balance)} / 充值 ${formatAmount(r.topped_up_balance)}）`,
				);
				const lines2 = lines.length > 0 ? lines.join("  ·  ") : "端点未返回任何币种行";
				ctx.ui.notify(
					`DeepSeek 余额：${lines2}｜可用性 ${balance.is_available === false ? "不足" : "正常"}`,
					"info",
				);
			} catch (err) {
				const hint = err instanceof AuthError ? "密钥被拒（401/403）" : `查询失败：${String(err)}`;
				ctx.ui.notify(`DeepSeek 余额${hint}`, "error");
			}
		},
	});
}
