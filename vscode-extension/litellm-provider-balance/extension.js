// Minimal, unpublished, local-only VS Code extension.
// Status bar credit/balance indicator for the providers behind (or adjacent
// to) your LiteLLM proxy: OpenRouter, DeepInfra, Fireworks AI, Anthropic,
// Google Gemini.
//
// Automatic (real provider APIs, both sides of the math):
//   - OpenRouter: GET /api/v1/credits -> total_credits, total_usage
//   - DeepInfra:  GET /v1/me?checklist=true -> stripe_balance (+ optional limit)
//
// Semi-automatic (real "spent" API, manual "total budget"):
//   - Fireworks AI: GET /v1/accounts/{id}/billing/summary -> spent since a
//     start date you set once; you tell it your total budget/top-ups.
//     Fireworks has no "remaining balance" endpoint at all, so this is the
//     best available estimate, not an authoritative number.
//
// Fully manual (no public usage API for a normal key):
//   - Anthropic, Gemini: you periodically glance at their console and type
//     in "total budget" + "spent so far"; the extension just subtracts,
//     colors, and tracks how stale that manual reading is.

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");

const SECRETS = {
  openrouterKey: "litellmBalance.openrouterKey",
  deepinfraKey: "litellmBalance.deepinfraKey",
  fireworksKey: "litellmBalance.fireworksKey",
  fireworksAccountId: "litellmBalance.fireworksAccountId",
};

const STATE_KEYS = {
  fireworksTotalBudget: "litellmBalance.fireworks.totalBudget",
  fireworksStartDate: "litellmBalance.fireworks.startDate",
  anthropicTotalBudget: "litellmBalance.anthropic.totalBudget",
  anthropicSpent: "litellmBalance.anthropic.spent",
  anthropicUpdatedAt: "litellmBalance.anthropic.updatedAt",
  geminiTotalBudget: "litellmBalance.gemini.totalBudget",
  geminiSpent: "litellmBalance.gemini.spent",
  geminiUpdatedAt: "litellmBalance.gemini.updatedAt",
};

const REFRESH_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

let statusBarItem;
let refreshTimer;
let last = {}; // provider key -> { remaining, total, error, manual, updatedAt }

// ---------- generic helpers ----------

function parseEnvFile(filePath) {
  const out = {};
  try {
    const text = fs.readFileSync(filePath, "utf8");
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq === -1) continue;
      const key = line.slice(0, eq).trim();
      let value = line.slice(eq + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      out[key] = value;
    }
  } catch {
    // no .env here, that's fine
  }
  return out;
}

function envFromWorkspace() {
  const merged = {};
  for (const folder of vscode.workspace.workspaceFolders || []) {
    Object.assign(merged, parseEnvFile(path.join(folder.uri.fsPath, ".env")));
  }
  return merged;
}

async function getSecretOrEnv(context, envMap, envVarName, secretKey) {
  if (envMap[envVarName]) return envMap[envVarName];
  return await context.secrets.get(secretKey);
}

async function promptSecret(context, secretKey, label, opts = {}) {
  const value = await vscode.window.showInputBox({
    prompt: label,
    password: !!opts.password,
    ignoreFocusOut: true,
    value: opts.value,
  });
  if (value !== undefined && value !== "") {
    await context.secrets.store(secretKey, value.trim());
  }
  return value;
}

async function promptNumber(current, label) {
  const raw = await vscode.window.showInputBox({
    prompt: label,
    ignoreFocusOut: true,
    value: current != null ? String(current) : "",
    validateInput: (v) => (v === "" || isNaN(Number(v)) ? "Enter a number" : null),
  });
  if (raw === undefined || raw === "") return undefined;
  return Number(raw);
}

function money(n) {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

/** green < 75% used, yellow 75-95%, red >=95% or <=0 remaining. null total -> unknown. */
function colorFor(remaining, total) {
  if (total == null || !(total > 0)) return remaining != null && remaining <= 0 ? "red" : null;
  if (remaining <= 0) return "red";
  const usedFraction = 1 - remaining / total;
  if (usedFraction >= 0.95) return "red";
  if (usedFraction >= 0.75) return "yellow";
  return "green";
}

const DOT = { green: "🟢", yellow: "🟡", red: "🔴", null: "⚪" };

function daysAgo(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  return Math.floor(ms / (24 * 60 * 60 * 1000));
}

// ---------- OpenRouter (automatic) ----------

async function fetchOpenRouter(key) {
  const res = await fetch("https://openrouter.ai/api/v1/credits", {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  const total = json?.data?.total_credits ?? 0;
  const usage = json?.data?.total_usage ?? 0;
  return { remaining: total - usage, total };
}

// ---------- DeepInfra (automatic) ----------

async function fetchDeepInfra(key) {
  const res = await fetch("https://api.deepinfra.com/v1/me?checklist=true", {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  const stripeBalance = json?.stripe_balance ?? json?.checklist?.stripe_balance;
  const limit = json?.limit ?? json?.checklist?.limit ?? null;
  if (typeof stripeBalance !== "number") throw new Error("no stripe_balance in response");
  // negative stripe_balance = ready-to-spend credit; positive = owed.
  const remaining = -stripeBalance;
  const total = typeof limit === "number" ? limit : null;
  return { remaining, total, stripeBalance };
}

// ---------- Fireworks AI (semi-automatic) ----------

/** Accepts "YOUR_USERNAME" or "accounts/YOUR_USERNAME" (as shown in Fireworks' own
 * resource names / API responses) — normalizes to the bare id either way. */
function normalizeFireworksAccountId(raw) {
  return String(raw || "")
    .trim()
    .replace(/^accounts\//, "")
    .replace(/\/$/, "");
}

async function fetchFireworksSpent(key, accountId, startIso, endIso) {
  const id = normalizeFireworksAccountId(accountId);
  const url = new URL(`https://api.fireworks.ai/v1/accounts/${id}/billing/summary`);
  url.searchParams.set("startTime", startIso);
  url.searchParams.set("endTime", endIso);
  url.searchParams.set("granularity", "GRANULARITY_UNSPECIFIED");
  const res = await fetch(url, { headers: { Authorization: `Bearer ${key}` } });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} on account "${id}"${body ? ` — ${body.slice(0, 200)}` : ""}`);
  }
  const json = await res.json();
  let spent = 0;
  for (const item of json?.lineItems || []) {
    const units = Number(item?.totalCost?.units ?? 0);
    const nanos = Number(item?.totalCost?.nanos ?? 0);
    spent += units + nanos / 1e9;
  }
  return spent;
}

async function computeFireworks(context, envMap) {
  const key = await getSecretOrEnv(context, envMap, "FIREWORKS_AI_API_KEY", SECRETS.fireworksKey);
  const accountId = await context.secrets.get(SECRETS.fireworksAccountId);
  const totalBudget = context.globalState.get(STATE_KEYS.fireworksTotalBudget);
  const startDate = context.globalState.get(STATE_KEYS.fireworksStartDate);

  if (!key || !accountId || totalBudget == null || !startDate) {
    return { configured: false };
  }
  const spent = await fetchFireworksSpent(key, accountId, startDate, new Date().toISOString());
  return { configured: true, remaining: totalBudget - spent, total: totalBudget, spent };
}

async function configureFireworks(context, envMap) {
  const existingKey = await getSecretOrEnv(context, envMap, "FIREWORKS_AI_API_KEY", SECRETS.fireworksKey);
  if (!existingKey) {
    await promptSecret(context, SECRETS.fireworksKey, "Fireworks AI API key", { password: true });
  }
  const existingAccountId = await context.secrets.get(SECRETS.fireworksAccountId);
  const rawAccountId = await vscode.window.showInputBox({
    prompt: 'Fireworks account ID — just the short id (e.g. "YOUR_USERNAME"), "accounts/" prefix is stripped automatically if pasted',
    ignoreFocusOut: true,
    value: existingAccountId,
  });
  if (rawAccountId !== undefined && rawAccountId !== "") {
    await context.secrets.store(SECRETS.fireworksAccountId, normalizeFireworksAccountId(rawAccountId));
  }
  const currentBudget = context.globalState.get(STATE_KEYS.fireworksTotalBudget);
  const budget = await promptNumber(
    currentBudget,
    "Total $ you've topped up on Fireworks (lifetime, like OpenRouter's total credits)"
  );
  if (budget !== undefined) {
    await context.globalState.update(STATE_KEYS.fireworksTotalBudget, budget);
  }
  if (!context.globalState.get(STATE_KEYS.fireworksStartDate)) {
    // Only set once: the point from which we start summing billing-summary spend.
    await context.globalState.update(STATE_KEYS.fireworksStartDate, new Date().toISOString());
  }
}

async function addFireworksTopUp(context) {
  const amount = await promptNumber(undefined, "Amount ($) you just added to Fireworks");
  if (amount === undefined) return;
  const current = context.globalState.get(STATE_KEYS.fireworksTotalBudget) || 0;
  await context.globalState.update(STATE_KEYS.fireworksTotalBudget, current + amount);
}

// ---------- Manual providers: Anthropic, Gemini ----------

function manualState(context, prefix) {
  return {
    total: context.globalState.get(STATE_KEYS[`${prefix}TotalBudget`]),
    spent: context.globalState.get(STATE_KEYS[`${prefix}Spent`]),
    updatedAt: context.globalState.get(STATE_KEYS[`${prefix}UpdatedAt`]),
  };
}

async function updateManual(context, prefix, label) {
  const { total, spent } = manualState(context, prefix);
  const newTotal = await promptNumber(total, `${label}: total $ budget (lifetime top-ups / plan limit)`);
  const newSpent = await promptNumber(spent, `${label}: $ spent so far (from their console/dashboard)`);
  if (newTotal !== undefined) await context.globalState.update(STATE_KEYS[`${prefix}TotalBudget`], newTotal);
  if (newSpent !== undefined) await context.globalState.update(STATE_KEYS[`${prefix}Spent`], newSpent);
  if (newTotal !== undefined || newSpent !== undefined) {
    await context.globalState.update(STATE_KEYS[`${prefix}UpdatedAt`], new Date().toISOString());
  }
}

function computeManual(context, prefix) {
  const { total, spent, updatedAt } = manualState(context, prefix);
  if (total == null || spent == null) return { configured: false };
  return { configured: true, remaining: total - spent, total, spent, updatedAt };
}

// ---------- refresh + render ----------

async function refresh(context, { silent } = {}) {
  const envMap = envFromWorkspace();
  const next = {};

  const orKey = await getSecretOrEnv(context, envMap, "OPENROUTER_API_KEY", SECRETS.openrouterKey);
  if (orKey) {
    try {
      next.openrouter = await fetchOpenRouter(orKey);
    } catch (e) {
      next.openrouter = { error: String(e.message || e) };
    }
  }

  const diKey = await getSecretOrEnv(context, envMap, "DEEPINFRA_API_KEY", SECRETS.deepinfraKey);
  if (diKey) {
    try {
      next.deepinfra = await fetchDeepInfra(diKey);
    } catch (e) {
      next.deepinfra = { error: String(e.message || e) };
    }
  }

  try {
    const fw = await computeFireworks(context, envMap);
    next.fireworks = fw.configured ? fw : { configured: false };
  } catch (e) {
    next.fireworks = { error: String(e.message || e) };
  }

  next.anthropic = computeManual(context, "anthropic");
  next.gemini = computeManual(context, "gemini");

  last = next;
  render({ orKeySet: !!orKey, diKeySet: !!diKey });

  if (!silent) {
    vscode.window.setStatusBarMessage("LiteLLM Providers: balances refreshed", 3000);
  }
}

function segment(label, keySet, entry) {
  if (entry?.error) return `${DOT.null} ${label}: error`;
  if (!keySet && entry === undefined) return `${DOT.null} ${label}: set key`;
  if (entry && entry.configured === false) return `${DOT.null} ${label}: setup`;
  if (!entry) return `${DOT.null} ${label}: n/a`;
  const color = colorFor(entry.remaining, entry.total);
  return `${DOT[color]} ${label} ${money(entry.remaining)}`;
}

/** Sums $ remaining across every provider with a usable number, and
 * separately sums $ total across those that also have a known budget
 * denominator (so the aggregate color reflects only providers where
 * "% used" is actually meaningful — e.g. DeepInfra with no spending limit
 * set contributes its $ remaining but not to the color calculation). */
function computeGrandTotal() {
  const entries = [last.openrouter, last.deepinfra, last.fireworks, last.anthropic, last.gemini];
  let sumRemaining = 0;
  let sumTotal = 0;
  let anyRemaining = false;
  let anyTotalKnown = false;

  for (const e of entries) {
    if (!e || e.error || e.configured === false) continue;
    if (typeof e.remaining === "number") {
      sumRemaining += e.remaining;
      anyRemaining = true;
    }
    if (typeof e.total === "number") {
      sumTotal += e.total;
      anyTotalKnown = true;
    }
  }

  if (!anyRemaining) return null;
  return {
    remaining: sumRemaining,
    total: anyTotalKnown ? sumTotal : null,
  };
}

function render({ orKeySet, diKeySet }) {
  const parts = [
    segment("OR", orKeySet, last.openrouter),
    segment("DI", diKeySet, last.deepinfra),
    segment("FW", true, last.fireworks),
    segment("Claude", true, last.anthropic),
    segment("Gemini", true, last.gemini),
  ];

  const grandTotal = computeGrandTotal();
  if (grandTotal) {
    const color = colorFor(grandTotal.remaining, grandTotal.total);
    parts.push(`${DOT[color]} Σ ${money(grandTotal.remaining)}`);
  }

  statusBarItem.text = parts.join("  ·  ");
  statusBarItem.tooltip = buildTooltip(grandTotal);
  statusBarItem.show();
}

function line(label, entry, opts = {}) {
  if (!entry) return `- ${label}: no API key configured`;
  if (entry.error) return `- ${label}: error — ${entry.error}`;
  if (entry.configured === false) return `- ${label}: not set up yet (see menu)`;
  const staleness = opts.manual ? ` _(manual, updated ${daysAgo(entry.updatedAt) ?? "?"}d ago)_` : "";
  return `- ${label}: ${money(entry.remaining)} remaining of ${money(entry.total)}${staleness}`;
}

function buildTooltip(grandTotal) {
  const lines = [
    "**Provider balances**",
    "",
    line("OpenRouter", last.openrouter),
    line("DeepInfra", last.deepinfra),
    line("Fireworks AI", last.fireworks) + " _(spend auto-tracked, budget manual)_",
    line("Anthropic (Claude)", last.anthropic, { manual: true }),
    line("Google Gemini", last.gemini, { manual: true }),
    "",
  ];

  if (grandTotal) {
    lines.push(
      grandTotal.total != null
        ? `**Total: ${money(grandTotal.remaining)} remaining of ${money(grandTotal.total)}**`
        : `**Total: ${money(grandTotal.remaining)} remaining** _(partial — some providers have no known budget total)_`
    );
    lines.push("");
  }

  lines.push("Click for options.");
  return new vscode.MarkdownString(lines.join("\n"));
}

// ---------- menu ----------

async function showMenu(context) {
  const picked = await vscode.window.showQuickPick(
    [
      { label: "$(refresh) Refresh now", action: "refresh" },
      { label: "$(key) Set/update OpenRouter API key", action: "setOpenRouter" },
      { label: "$(key) Set/update DeepInfra API key", action: "setDeepInfra" },
      { label: "$(gear) Configure Fireworks tracking (key, account ID, budget)", action: "configFireworks" },
      { label: "$(add) Record a Fireworks top-up", action: "topUpFireworks" },
      { label: "$(edit) Update Anthropic (Claude) budget & spent-so-far", action: "updateAnthropic" },
      { label: "$(edit) Update Google Gemini budget & spent-so-far", action: "updateGemini" },
      { label: "$(link-external) Open OpenRouter dashboard", action: "openOpenRouter" },
      { label: "$(link-external) Open DeepInfra dashboard", action: "openDeepInfra" },
      { label: "$(link-external) Open Fireworks AI billing dashboard", action: "openFireworks" },
      { label: "$(link-external) Open Anthropic Console usage page", action: "openAnthropic" },
      { label: "$(link-external) Open Google AI Studio usage page", action: "openGemini" },
    ],
    { title: "LiteLLM Provider Balances" }
  );
  if (!picked) return;

  const envMap = envFromWorkspace();
  switch (picked.action) {
    case "refresh":
      await refresh(context);
      return;
    case "setOpenRouter":
      await promptSecret(context, SECRETS.openrouterKey, "OpenRouter API key", { password: true });
      break;
    case "setDeepInfra":
      await promptSecret(context, SECRETS.deepinfraKey, "DeepInfra API key", { password: true });
      break;
    case "configFireworks":
      await configureFireworks(context, envMap);
      break;
    case "topUpFireworks":
      await addFireworksTopUp(context);
      break;
    case "updateAnthropic":
      await updateManual(context, "anthropic", "Anthropic (Claude)");
      break;
    case "updateGemini":
      await updateManual(context, "gemini", "Google Gemini");
      break;
    case "openOpenRouter":
      vscode.env.openExternal(vscode.Uri.parse("https://openrouter.ai/settings/credits"));
      return;
    case "openDeepInfra":
      vscode.env.openExternal(vscode.Uri.parse("https://deepinfra.com/dash/billing"));
      return;
    case "openFireworks":
      vscode.env.openExternal(vscode.Uri.parse("https://fireworks.ai/account/billing"));
      return;
    case "openAnthropic":
      vscode.env.openExternal(vscode.Uri.parse("https://console.anthropic.com/settings/usage"));
      return;
    case "openGemini":
      vscode.env.openExternal(vscode.Uri.parse("https://aistudio.google.com/usage"));
      return;
  }
  await refresh(context, { silent: true });
}

// ---------- activation ----------

function activate(context) {
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = "litellmBalance.showMenu";
  context.subscriptions.push(statusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand("litellmBalance.refresh", () => refresh(context)),
    vscode.commands.registerCommand("litellmBalance.showMenu", () => showMenu(context))
  );

  refresh(context, { silent: true });
  refreshTimer = setInterval(() => refresh(context, { silent: true }), REFRESH_INTERVAL_MS);
  context.subscriptions.push({ dispose: () => clearInterval(refreshTimer) });
}

function deactivate() {
  if (refreshTimer) clearInterval(refreshTimer);
}

module.exports = { activate, deactivate };
