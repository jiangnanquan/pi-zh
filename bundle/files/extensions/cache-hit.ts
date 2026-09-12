/**
 * cache-hit — 状态栏显示最近一次请求的 prompt cache 命中率（等价 pi 内置 footer 的 `CH`）。
 *
 * 为什么单独做：DeepSeek 的缓存命中直接决定成本 —— deepseek-flash 的
 * cacheRead 定价 $0.006/M 对比 input $0.3/M（50 倍差价）。命中率掉下来
 * 往往意味着 prompt 前缀被改动（系统提示、工具列表、技能清单变动）。
 *
 * 口径：状态栏 = `CH <实时>% (累计 <累计>%)`
 *   实时 = 最近一次 assistant 请求的 `cacheRead / (input + cacheRead + cacheWrite)`
 *          —— 与 pi 内置 footer 的 CH 一致，反映"当下缓存是否还生效"。
 *   累计 = 本会话全部有效请求的 `ΣcacheRead / (Σinput + ΣcacheRead + ΣcacheWrite)`
 *          —— 2026-09-12 起合并进本段，取代 pi-powerline-footer 内置的 `cache_read`
 *             段（该段口径不含 cacheWrite；在 cacheWrite 恒为 0 的 DeepSeek 上与这里
 *             完全等价，唯一区别是累计 vs 实时，故不再单列）。
 *   报告   = `/ch` 给出最近 10 轮明细与会话累计命中率、缓存节省金额。
 * 会话首轮 cacheRead 必为 0（冷启动，无缓存可命中），此时用 dim 色显示 0.0%
 * 以免误判为异常；此后按阈值着色。
 *
 * 空 usage 记录（provider 偶发返回 in/cR/cW 全 0，实测本机 2026-09-12 某会话第 23 轮）：
 *   对累计**比率**是 no-op（分子分母同为 0），但会污染请求计数与逐行明细，
 *   因此计数、明细与累计一律跳过它；只有含真实 prompt token 的记录才参与统计。
 *
 * 环境变量：
 *   PI_CACHE_HIT_THRESHOLDS  `"95,80"` 命中率阈值（百分数：警告,告急；0 关闭该档）
 *
 * 配合 pi-powerline-footer 时在 settings.json 提升为 footer segment：
 *   "powerline": { "customItems": [
 *     { "id": "cache-hit", "statusKey": "cache-hit", "position": "right", "selfColorize": true } ] }
 *
 * 命令：`/ch` 输出最近若干轮命中率明细与累计节省。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const STATUS_KEY = "cache-hit";
const REPORT_ROWS = 10;

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

type Usage = {
	input?: number;
	output?: number;
	cacheRead?: number;
	cacheWrite?: number;
	cost?: { total?: number };
};

type ModelCost = { input?: number; output?: number; cacheRead?: number; cacheWrite?: number };

type UiLike = {
	setStatus: (key: string, text?: string) => void;
	notify: (message: string, level?: "info" | "warning" | "error") => void;
	theme: { fg: (color: string, text: string) => string };
};

type CtxLike = {
	ui: UiLike;
	mode?: string;
	hasUI?: boolean;
	model?: { provider?: string; id?: string; cost?: ModelCost };
	sessionManager?: { getBranch: () => Array<{ type?: string; message?: { role?: string; usage?: Usage } }> };
};

type Thresholds = { warn: number; urgent: number };

// ---------------------------------------------------------------------------
// 纯函数
// ---------------------------------------------------------------------------

/** 阈值解析：`"95,80"` → {warn:95, urgent:80}；0 表示关闭该档 */
export function parseThresholds(raw: string | undefined): Thresholds {
	const parts = (raw ?? "95,80")
		.split(",")
		.map((s) => Number(s.trim()))
		.filter((n) => Number.isFinite(n) && n >= 0);
	return { warn: parts[0] ?? 95, urgent: parts[1] ?? 80 };
}

/** 空 usage 记录：in/cR/cW 全 0，既非命中亦非未命中，不参与计数、明细与累计 */
export function isEmptyUsage(usage: Usage | undefined): boolean {
	if (!usage) return true;
	return (usage.input ?? 0) === 0 && (usage.cacheRead ?? 0) === 0 && (usage.cacheWrite ?? 0) === 0;
}

/** 会话累计命中率（百分数）：跳过空 usage 记录；无有效 prompt token 时返回 null */
export function cumulativeRateOf(usages: readonly Usage[]): number | null {
	let miss = 0;
	let read = 0;
	let write = 0;
	for (const u of usages) {
		if (isEmptyUsage(u)) continue;
		miss += u.input ?? 0;
		read += u.cacheRead ?? 0;
		write += u.cacheWrite ?? 0;
	}
	const total = miss + read + write;
	return total > 0 ? (read / total) * 100 : null;
}

/** 命中率（百分数）：cacheRead 占整个 prompt 的比重；无 prompt token 时返回 null */
export function hitRateOf(usage: Usage | undefined): number | null {
	if (!usage) return null;
	const miss = usage.input ?? 0;
	const read = usage.cacheRead ?? 0;
	const write = usage.cacheWrite ?? 0;
	const total = miss + read + write;
	if (total <= 0) return null;
	return (read / total) * 100;
}

/** 命中率对应的主题色名 */
function colorFor(rate: number, t: Thresholds): string {
	if (t.urgent > 0 && rate < t.urgent) return "error";
	if (t.warn > 0 && rate < t.warn) return "warning";
	return "accent";
}

/** token 数格式化：12.4k / 5.48M */
function formatTokens(n: number): string {
	if (!Number.isFinite(n)) return "?";
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
	if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
	return String(n);
}

// ---------------------------------------------------------------------------
// 扩展主体
// ---------------------------------------------------------------------------

export default function cacheHit(pi: ExtensionAPI): void {
	const env = process.env as Record<string, string | undefined>;
	const thresholds = parseThresholds(env["PI_CACHE_HIT_THRESHOLDS"]);

	let lastUsage: Usage | undefined;
	let lastRate: number | null = null;
	let lastCumulative: number | null = null;
	let requestCount = 0;
	let lastUi: UiLike | null = null;

	function render(ui: UiLike): void {
		if (lastRate === null) {
			ui.setStatus(STATUS_KEY, undefined);
			return;
		}
		const text = lastCumulative === null
			? `CH ${lastRate.toFixed(1)}%`
			: `CH ${lastRate.toFixed(1)}% (累计 ${lastCumulative.toFixed(0)}%)`;
		// 会话首轮必然 0%（冷启动，无缓存可命中），用 dim 避免误判为缓存失效
		const coldStart = requestCount <= 1 && (lastUsage?.cacheRead ?? 0) === 0;
		ui.setStatus(STATUS_KEY, ui.theme.fg(coldStart ? "dim" : colorFor(lastRate, thresholds), text));
	}

	/** 从会话分支收集所有 assistant 请求的 usage */
	function collectUsages(ctx: CtxLike): Usage[] {
		const out: Usage[] = [];
		for (const entry of ctx.sessionManager?.getBranch?.() ?? []) {
			if (entry?.type === "message" && entry.message?.role === "assistant" && entry.message.usage) {
				out.push(entry.message.usage);
			}
		}
		return out;
	}

	/**
	 * 从会话历史恢复最近一次请求的命中率。
	 * /reload 重载扩展会清空内存状态，而 message_end 只在请求结束后触发；
	 * 恢复会话（pi -c）时分支里也已有历史 —— 两者都靠这里避免 segment 空白。
	 */
	function restoreFromHistory(ctx: CtxLike): boolean {
		const usages = collectUsages(ctx);
		if (usages.length === 0) return false;
		// 末尾可能是空 usage 记录（provider 偶发），回退到最近一条有效记录
		let latest: Usage | undefined;
		for (let i = usages.length - 1; i >= 0; i--) {
			if (!isEmptyUsage(usages[i])) {
				latest = usages[i];
				break;
			}
		}
		const rate = hitRateOf(latest);
		if (rate === null) return false;
		lastUsage = latest;
		lastRate = rate;
		lastCumulative = cumulativeRateOf(usages);
		requestCount = usages.length;
		return true;
	}

	pi.on("message_end", async (eventRaw: unknown, ctxRaw: unknown) => {
		const ctx = ctxRaw as CtxLike;
		const message = (eventRaw as { message?: { role?: string; usage?: Usage } })?.message;
		if (message?.role !== "assistant" || !message.usage) return;

		const rate = hitRateOf(message.usage);
		if (rate === null) return;

		lastUsage = message.usage;
		lastRate = rate;
		requestCount += 1;
		lastUi = ctx.ui;

		// 累计从会话分支重建。message_end 时本条消息可能尚未落进分支，
		// 因此按**对象同一性**补一次（已在分支里就不重复计入）。
		const usages = collectUsages(ctx);
		if (!usages.some((u) => u === message.usage)) usages.push(message.usage);
		lastCumulative = cumulativeRateOf(usages);

		render(ctx.ui);
	});

	pi.on("session_start", async (_event: unknown, ctxRaw: unknown) => {
		const ctx = ctxRaw as CtxLike;
		lastUsage = undefined;
		lastRate = null;
		lastCumulative = null;
		requestCount = 0;
		lastUi = ctx.ui;
		restoreFromHistory(ctx); // 恢复会话时分支已有历史，立即显示上次命中率
		render(ctx.ui);
	});

	// /reload 重载扩展不保证重发 session_start，因此每轮开始补一次历史恢复
	pi.on("turn_start", async (_event: unknown, ctxRaw: unknown) => {
		const ctx = ctxRaw as CtxLike;
		lastUi = ctx.ui;
		if (lastRate === null && restoreFromHistory(ctx)) render(ctx.ui);
	});

	pi.on("session_shutdown", async () => {
		// 与其他 footer 扩展（tps-status / context-bar）对齐：清内存的同时清状态栏文本，
		// 否则会话切换时旧值会残留到下一次 session_start 的首次 render 之前。
		lastUi?.setStatus(STATUS_KEY, undefined);
		requestCount = 0;
		lastRate = null;
		lastCumulative = null;
		lastUsage = undefined;
		lastUi = null;
	});

	pi.registerCommand("ch", {
		description: "缓存命中率明细：最近若干轮 + 会话累计与缓存节省（空 usage 记录已跳过）",
		handler: async (_args: string, ctxRaw: unknown) => {
			const ctx = ctxRaw as CtxLike;
			lastUi = ctx.ui;
			const usages = collectUsages(ctx);
			// 累计与明细跳过空 usage 记录（对比率是 no-op，但会污染计数与逐行明细）
			const valid = usages.filter((u) => !isEmptyUsage(u));
			const skipped = usages.length - valid.length;
			if (valid.length === 0) {
				ctx.ui.notify(
					skipped > 0
						? `本会话仅有 ${skipped} 条空 usage 记录（in/cR/cW 全 0），没有可统计的请求。`
						: "本会话尚无带 usage 的 assistant 请求。",
					"info",
				);
				return;
			}

			// 状态栏同步为最新一轮（命令可能在新会话/重载后先被调用）
			restoreFromHistory(ctx);
			render(ctx.ui);

			const sum = { miss: 0, read: 0, write: 0 };
			for (const u of valid) {
				sum.miss += u.input ?? 0;
				sum.read += u.cacheRead ?? 0;
				sum.write += u.cacheWrite ?? 0;
			}
			const totalPrompt = sum.miss + sum.read + sum.write;
			const cumulative = cumulativeRateOf(usages) ?? 0;

			// 成本视角：cacheRead 若按 input 价计费需要多少钱（定价单位 $/1M tokens）
			const modelCost: ModelCost = ctx.model?.cost ?? {};
			const readPrice = modelCost.cacheRead ?? 0;
			const missPrice = modelCost.input ?? 0;
			const actual = (sum.read * readPrice) / 1e6;
			const withoutCache = (sum.read * missPrice) / 1e6;
			const saved = withoutCache - actual;

			const rows = valid.slice(-REPORT_ROWS).map((u, i) => {
				const idx = valid.length - Math.min(REPORT_ROWS, valid.length) + i + 1;
				const rate = hitRateOf(u) ?? 0;
				return `  #${idx} ${rate.toFixed(1)}%  cache ${formatTokens(u.cacheRead ?? 0)}，miss ${formatTokens(u.input ?? 0)}`;
			});

			const lines = [
				`缓存命中率（最近 ${rows.length} 轮，共 ${valid.length} 次有效请求${skipped > 0 ? `，另有 ${skipped} 条空 usage 记录已跳过` : ""}）`,
				...rows,
				"",
				`累计命中率：${cumulative.toFixed(1)}%（cacheRead ${formatTokens(sum.read)} / prompt ${formatTokens(totalPrompt)}）`,
				missPrice > 0 && readPrice > 0
					? `缓存节省：$ ${saved.toFixed(4)}（实际 $ ${actual.toFixed(4)}，若无缓存 $ ${withoutCache.toFixed(4)}）`
					: "缓存节省：当前模型未配置 cacheRead/input 定价，跳过估算",
			];
			ctx.ui.notify(lines.join("\n"), cumulative >= thresholds.warn ? "info" : "warning");
		},
	});
}
