/* Option Riders — Trade Journal front-end */

const $ = (id) => document.getElementById(id);

const AUTO_SYNC_MS = 15 * 60 * 1000;
const BASE_CURRENCY = "USD"; // IBKR account currency for our data

let _supabase = null;
let _session = null;
let _memoryCreds = null;
let _journalProfile = null;
let _profileError = false;
async function loadJournalProfile() {
  const userId = _session?.user?.id;
  if (!userId) return;
  try {
    const result = await api("/api/journal/profile");
    if (_session?.user?.id !== userId) return;
    _journalProfile = result;
    _profileError = false;
    state.goalSettingsVersion = null;
    loadGoalSettings();
    renderRuleStars();
  } catch (_) {
    if (_session?.user?.id === userId) _profileError = true;
  }
}

let _connection = { enabled: false, connected: false };

function applyPrivacy(hidden) {
  document.body.classList.toggle("is-private", hidden);
  const button = $("privacyToggle");
  if (button) {
    button.textContent = hidden ? "Show P&L" : "Hide P&L";
    button.setAttribute("aria-pressed", String(hidden));
  }
}
function togglePrivacy() {
  const hidden = !document.body.classList.contains("is-private");
  applyPrivacy(hidden);
  try { localStorage.setItem("journal_hide_pnl", String(hidden)); } catch (_) {}
}


async function initAuth() {
  try {
    const cfg = await fetch("/api/public-config", { cache: "no-store" }).then(r => r.json());
    const url = cfg.supabaseUrl || cfg.SUPABASE_URL || cfg.supabase_url;
    const anon = cfg.supabaseAnonKey || cfg.SUPABASE_ANON_KEY || cfg.supabase_anon_key;
    if (url && anon && window.supabase) {
      _supabase = window.supabase.createClient(url, anon);
      const { data } = await _supabase.auth.getSession();
      _session = data.session || null;
      if (_session) {
        const { data: fresh } = await _supabase.auth.getUser();
        if (fresh?.user) _session.user = fresh.user;
      }
      _supabase.auth.onAuthStateChange((_e, session) => {
        const changedUser = _session?.user?.id !== session?.user?.id;
        _session = session;
        if (changedUser) {
          state.lastGoalPnl = null;
          document.body.classList.add("is-account-loading");
          state.activeNoteKey = null;
          closeTradeDetail();
          closeWeekModal();
          _memoryCreds = null;
          _journalProfile = null;
          _profileError = false;
          _connection = { enabled: false, connected: false };
          setAutoSync(false);
          $("settingsToken").value = $("settingsQueryId").value = "";
        }
        loadGoalSettings();
        renderRuleStars();
        if (changedUser) closeDayModal();
        applyAuthGate();
        if (changedUser && session) setTimeout(async () => { await Promise.all([loadJournalProfile(), loadConnection()]); refresh(); }, 0);
      });
    }
  } catch { /* Hosted pages remain gated on configuration failures. */ }
  applyAuthGate();
}

function applyAuthGate() {
  const gate = $("authGate");
  if (!gate) return;
  // Hosted pages fail closed when authentication configuration cannot load.
  const isLocal = ["localhost", "127.0.0.1", "::1"].includes(window.location?.hostname);
  if ((_supabase && !_session) || (!_supabase && !isLocal)) {
    gate.hidden = false;
    document.body.classList.add("is-gated");
  } else {
    gate.hidden = true;
    document.body.classList.remove("is-gated");
  }
}

async function signInWithGoogle() {
  if (!_supabase) return;
  await _supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin + "/journal.html" },
  });
}

const state = {
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth() + 1,
  currency: localStorage.getItem("journal_currency") || "GBP",
  lastEquity: [],
  autoSyncTimer: null,
  fxRate: 1.0,            // base → display
  baseAlreadyApplied: false,
  viewMode: localStorage.getItem("journal_view_mode") || "day",  // "day" | "week"
  noteSaveTimer: null,
  activeNoteKey: null,
  monthlyTarget: 5000,
  tradingDays: 20,
  lastGoalPnl: null,
  goalSettingsVersion: null,
  goalSaving: false,
  rulesDate: null,
  rulesSaving: false,
  dayRequest: 0,
};

const currencySymbol = { USD: "$", GBP: "£", EUR: "€" };

async function ensureFxRate() {
  // If backend already converted each trade into the account base currency
  // using IBKR's per-trade FXRateToBase, the numbers are already in GBP.
  // Don't apply a second conversion.
  if (state.baseAlreadyApplied) {
    state.fxRate = 1.0;
    return;
  }
  if (state.currency === BASE_CURRENCY) {
    state.fxRate = 1.0;
    return;
  }
  const cacheKey = `journal_fx_${BASE_CURRENCY}_${state.currency}`;
  const today = new Date().toISOString().slice(0, 10);
  const cached = JSON.parse(localStorage.getItem(cacheKey) || "null");
  if (cached && cached.date === today && typeof cached.rate === "number") {
    state.fxRate = cached.rate;
    return;
  }
  const sources = [
    `https://open.er-api.com/v6/latest/${BASE_CURRENCY}`,
    `https://api.frankfurter.app/latest?from=${BASE_CURRENCY}&to=${state.currency}`,
  ];
  for (const url of sources) {
    try {
      const res = await fetch(url);
      if (!res.ok) continue;
      const data = await res.json();
      const rate = data?.rates?.[state.currency];
      if (typeof rate === "number") {
        state.fxRate = rate;
        localStorage.setItem(cacheKey, JSON.stringify({ date: today, rate }));
        return;
      }
    } catch {}
  }
  // Fallback — conservative, user can toggle back to USD if they see old numbers
  const fallback = { GBP: 0.79, EUR: 0.93 };
  state.fxRate = fallback[state.currency] ?? 1.0;
}

function themeColor(name, fallback = "") {
  const val = getComputedStyle(document.body).getPropertyValue(`--${name}`).trim();
  return val || fallback;
}

// IBKR Flex timestamps are wall-clock America/New_York. We display in
// Europe/London (same as Lisbon) to match the user's locale and TradeZella.
const _IBKR_TZ = "America/New_York";
const _DISPLAY_TZ = "Europe/London";

function _nyWallClockToUtcMillis(Y, M, D, h, m, s) {
  // Build a Date from the NY wall clock, correcting for EDT/EST offset.
  // Start by treating the components as UTC, then find what NY thinks about
  // that moment, and adjust so the NY wall clock lines up with what we want.
  const naiveUtc = Date.UTC(Y, M - 1, D, h, m, s);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: _IBKR_TZ, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date(naiveUtc));
  const lookup = Object.fromEntries(parts.filter(p => p.type !== "literal").map(p => [p.type, p.value]));
  const nyUtc = Date.UTC(+lookup.year, +lookup.month - 1, +lookup.day,
                         +lookup.hour, +lookup.minute, +lookup.second);
  // naiveUtc was the wall clock as-if-UTC; nyUtc is that same moment rendered
  // in NY. The offset between them is NY's UTC offset at this moment.
  const offsetMs = naiveUtc - nyUtc;
  return naiveUtc + offsetMs;
}

function fmtDisplayTime(iso, withSeconds = true) {
  if (!iso || iso.length < 19) return "";
  try {
    const [datePart, timePart] = iso.split("T");
    const [Y, M, D] = datePart.split("-").map(Number);
    const [h, m, s] = timePart.slice(0, 8).split(":").map(Number);
    const utcMs = _nyWallClockToUtcMillis(Y, M, D, h, m, s);
    return new Date(utcMs).toLocaleTimeString("en-GB", {
      hour: "2-digit", minute: "2-digit",
      second: withSeconds ? "2-digit" : undefined,
      timeZone: _DISPLAY_TZ, hourCycle: "h23",
    });
  } catch (_) {
    return iso.slice(11, withSeconds ? 19 : 16);
  }
}

function fmtDisplayDate(iso) {
  // trade_date is a plain date (no TZ semantics) — just reformat MM/DD/YY.
  if (!iso) return "";
  const [Y, M, D] = iso.split("-");
  return Y ? `${M}/${D}/${Y.slice(2)}` : iso;
}

// Full weekday + date + time (in the display timezone) for a datetime ISO.
// Used where the day matters, e.g. a trade that opened and closed on
// different days — "14:32" alone can't tell you which day it was.
function fmtDisplayDateTime(iso, withSeconds = true) {
  if (!iso || iso.length < 19) return "";
  try {
    const [datePart, timePart] = iso.split("T");
    const [Y, M, D] = datePart.split("-").map(Number);
    const [h, m, s] = timePart.slice(0, 8).split(":").map(Number);
    const d = new Date(_nyWallClockToUtcMillis(Y, M, D, h, m, s));
    const dateStr = d.toLocaleDateString(undefined, {
      weekday: "short", month: "short", day: "2-digit", timeZone: _DISPLAY_TZ,
    });
    const timeStr = d.toLocaleTimeString("en-GB", {
      hour: "2-digit", minute: "2-digit",
      second: withSeconds ? "2-digit" : undefined,
      timeZone: _DISPLAY_TZ, hourCycle: "h23",
    });
    return `${dateStr} · ${timeStr}`;
  } catch (_) {
    return iso.slice(0, withSeconds ? 19 : 16).replace("T", " ");
  }
}

const fmt = {
  money(v, { sign = true, compact = false } = {}) {
    if (v == null || Number.isNaN(v)) return "—";
    const sym = currencySymbol[state.currency] || "$";
    const converted = v * state.fxRate;
    const abs = Math.abs(converted);
    let s;
    if (compact && abs >= 1000) {
      s = (abs / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "K";
    } else {
      s = abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    const prefix = sign && converted !== 0 ? (converted > 0 ? "+" : "−") : (converted < 0 ? "−" : "");
    return `${prefix}${sym}${s}`;
  },
  num(v, d = 2) {
    if (v == null || Number.isNaN(v)) return "—";
    return Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  },
  pct(v) {
    if (v == null || Number.isNaN(v)) return "—";
    return `${Number(v).toFixed(v >= 10 ? 1 : 2)}%`;
  },
};

function signClass(v) {
  if (v == null || v === 0) return "neutral";
  return v > 0 ? "pos" : "neg";
}

function formatSymbol(r) {
  const base = (r.underlying || r.symbol || "").trim();
  if (r.asset_class === "OPT" || r.asset_class === "FOP") {
    const pc = r.put_call === "P" ? "P" : r.put_call === "C" ? "C" : "";
    const strike = r.strike != null
      ? (Number.isInteger(r.strike) ? r.strike : Number(r.strike).toFixed(2).replace(/\.?0+$/, ""))
      : "";
    let exp = "";
    if (r.expiry) {
      const [y, m, d] = r.expiry.split("-");
      if (y) exp = `${parseInt(m, 10)}/${parseInt(d, 10)}/${y.slice(2)}`;
    }
    const strikeStr = strike ? `$${strike}${pc}` : pc;
    return `<span class="sym-base">${escapeHtml(base)}</span> <span class="sym-opt">${escapeHtml(strikeStr)}</span><span class="sym-exp">${escapeHtml(exp ? ` ${exp}` : "")}</span>`;
  }
  return `<span class="sym-base">${escapeHtml(base)}</span>`;
}

function buildQuery() {
  // Header filters (currency / asset / date range) were removed from the UI.
  // compute_stats / equity / fills still accept these params on the server,
  // so if we reintroduce filters elsewhere, set them here.
  return "";
}

async function api(path, opts = {}) {
  const userId = _session?.user?.id;
  const headers = new Headers(opts.headers || {});
  if (_session?.access_token) {
    headers.set("Authorization", `Bearer ${_session.access_token}`);
  }
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  const result = await res.json();
  if (_session?.user?.id !== userId) throw new Error("Account changed. Please retry.");
  return result;
}

async function refresh() {
  const userId = _session?.user?.id;
  const qs = buildQuery();
  $("statusLine").textContent = "Loading…";
  try {
    await ensureFxRate();
    const calQs = new URLSearchParams(qs);
    calQs.set("year", state.calYear);
    calQs.set("month", state.calMonth);

    // The Monthly Target path always tracks the CURRENT month, independent of
    // wherever the calendar has been navigated to.
    const now = new Date();
    const goalQs = new URLSearchParams(qs);
    goalQs.set("year", now.getFullYear());
    goalQs.set("month", now.getMonth() + 1);
    const goalIsCurrentCal = Number(state.calYear) === now.getFullYear()
      && Number(state.calMonth) === now.getMonth() + 1;

    const [stats, fills, equity, calendar, goalCal] = await Promise.all([
      api(`/api/journal/stats?${qs}`),
      api(`/api/journal/fills?${qs}&limit=300`),
      api(`/api/journal/equity?${qs}`),
      api(`/api/journal/calendar?${calQs.toString()}`),
      goalIsCurrentCal ? Promise.resolve(null)
                       : api(`/api/journal/calendar?${goalQs.toString()}`),
    ]);
    if (_session?.user?.id !== userId) return;
    state.baseAlreadyApplied = !!stats.base_currency_applied;
    await ensureFxRate();
    if (_session?.user?.id !== userId) return;
    state.lastEquity = equity;
    renderStats(stats);
    renderGoalPath((goalCal || calendar).month_pnl || 0);
    renderFarm(stats.net_pnl);
    renderSymbolTable(stats.by_symbol);
    renderDayTable(stats.by_day);
    renderRecentTrades(fills);
    renderFills(fills);
    renderCalendar(calendar);
    document.body.classList.remove("is-account-loading");
    drawEquity(equity);
    $("statusLine").textContent = stats.trade_count === 0
      ? "No trades yet — import a Flex CSV to begin."
      : `${stats.trade_count} fills · ${stats.close_count} closed trades · updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    $("statusLine").textContent = `Error: ${escapeHtml(err.message)}`;
  }
}

/* ---------- stats ---------- */

function zellaScore(s) {
  // Composite out of 100 — gives a single "how am I doing" number.
  const win = Math.min(100, s.win_rate || 0);
  const pf = Math.max(0, Math.min(100, (s.profit_factor || 0) * 40));
  const exp = Math.max(0, Math.min(100, 50 + (s.expectancy || 0) / 10));
  const wl = s.avg_loss
    ? Math.max(0, Math.min(100, ((s.avg_win || 0) / Math.abs(s.avg_loss)) * 50))
    : (s.avg_win ? 100 : 50);
  return Math.round((win * 0.3 + pf * 0.3 + exp * 0.2 + wl * 0.2) * 10) / 10;
}

/* ---------- Personal monthly target ---------- */

const DEFAULT_GOAL = { monthlyTarget: 5000, tradingDays: 20 };


function validGoalSettings(value) {
  if (!value || typeof value.monthlyTarget !== "number" || typeof value.tradingDays !== "number") return null;
  const { monthlyTarget, tradingDays } = value;
  if (!Number.isFinite(monthlyTarget) || monthlyTarget < 0.01 || monthlyTarget > 999999999.99
      || !Number.isInteger(tradingDays) || tradingDays < 1 || tradingDays > 31) return null;
  return { monthlyTarget: Math.round(monthlyTarget * 100) / 100, tradingDays };
}

function goalMoney(value) {
  // Targets are entered in the display currency, not in the feed's base currency.
  return `${currencySymbol[state.currency] || "$"}${fmt.num(value, Number.isInteger(value) ? 0 : 2)}`;
}

function goalMetadataKey() { return `journal_goal_${state.currency}`; }

function loadGoalSettings() {
  let saved = _journalProfile?.enabled ? _journalProfile.goals?.[state.currency] : _session?.user?.user_metadata?.[goalMetadataKey()];
  if (!_supabase) {
    try { saved = JSON.parse(localStorage.getItem(`journal_goal_local:${state.currency}`)); } catch (_) {}
  }
  const prefs = validGoalSettings(saved) || DEFAULT_GOAL;
  const version = JSON.stringify([_session?.user?.id || "local", state.currency, prefs]);
  if (state.goalSettingsVersion === version) return; // Token refresh must not erase an unsaved edit.
  state.goalSettingsVersion = version;
  state.monthlyTarget = prefs.monthlyTarget;
  state.tradingDays = prefs.tradingDays;
  $("goalMonthlyInput").value = prefs.monthlyTarget;
  $("goalDaysInput").value = prefs.tradingDays;
  $("goalCurrencyLabel").textContent = `Monthly target (${state.currency})`;
  $("goalSaveStatus").textContent = "";
  previewDailyTarget();
  renderGoalPlan();
  renderGoalPath(state.lastGoalPnl);
}

function previewDailyTarget() {
  const prefs = validGoalSettings({ monthlyTarget: Number($("goalMonthlyInput").value),
    tradingDays: Number($("goalDaysInput").value) });
  $("goalDailyPreview").textContent = prefs ? `${goalMoney(prefs.monthlyTarget / prefs.tradingDays)} / day` : "Enter a positive target and 1–31 trading days";
}

async function saveGoalSettings(event) {
  event.preventDefault();
  if (state.goalSaving || !$("goalSettingsForm").reportValidity()) return;
  const prefs = validGoalSettings({ monthlyTarget: Number($("goalMonthlyInput").value),
    tradingDays: Number($("goalDaysInput").value) });
  const status = $("goalSaveStatus");
  if (!prefs) { status.textContent = "Enter a positive target and 1–31 whole trading days."; return; }
  const userId = _session?.user?.id;
  const currency = state.currency;
  const metadataKey = goalMetadataKey();
  state.goalSaving = true;
  $("goalSaveButton").disabled = true;
  $("goalMonthlyInput").disabled = $("goalDaysInput").disabled = true;
  status.textContent = "Saving…";
  try {
    if (_supabase) {
      if (!userId) throw new Error("Sign in to save your target.");
      if (_profileError) throw new Error("Could not load your saved plan. Refresh and retry.");
      if (_journalProfile?.enabled) {
        await api("/api/journal/profile", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({kind:"goal", currency, ...prefs})});
        if (_session?.user?.id !== userId) return;
        _journalProfile.goals[currency] = prefs;
        if (state.currency !== currency) return;
      } else {
        const { data, error } = await _supabase.auth.updateUser({ data: { [metadataKey]: prefs } });
        if (error) throw error;
        if (_session?.user?.id !== userId || state.currency !== currency) return;
        _session.user = data.user;
      }
    } else {
      localStorage.setItem(`journal_goal_local:${currency}`, JSON.stringify(prefs));
    }
    state.goalSettingsVersion = null;
    loadGoalSettings();
    status.textContent = _supabase ? "Target saved to your account." : "Target saved in this browser.";
  } catch (error) {
    if (_session?.user?.id === userId && state.currency === currency) status.textContent = `Not saved: ${error.message}`;
  } finally {
    state.goalSaving = false;
    $("goalSaveButton").disabled = false;
    $("goalMonthlyInput").disabled = $("goalDaysInput").disabled = false;
  }
}

function renderGoalPlan() {
  const target = state.monthlyTarget, days = state.tradingDays, daily = target / days;
  $("goalSub").textContent = "Progress resets on the 1st";
  $("goalOf").textContent = `of ${goalMoney(target)} this month`;
  $("goalDailyTarget").textContent = `${goalMoney(daily)} daily target · ${days} planned trading days`;
  $("whyMonthlyTarget").textContent = goalMoney(target);
  $("whyDailyTarget").textContent = goalMoney(daily);
  $("whyWeeklyTarget").textContent = goalMoney(daily * 5);
  $("whyMonthTarget").textContent = goalMoney(target);
  $("whyYearTarget").textContent = goalMoney(target * 12);
  $("whyPlanNote").textContent = `${goalMoney(daily)} a day across ${days} planned trading days per month. Week assumes five trading days; year assumes twelve months. These are targets, not forecasts.`;
  $("whyDailyGate").textContent = `Sized to the plan? ${goalMoney(daily)} today is a whole day well spent.`;
}

// Equal-distance pieces along a smooth curve keep every daily target the same size.
function goalPathSegments(count) {
  const points = [], lengths = [0];
  for (let i = 0; i <= 600; i++) {
    const t = i / 600;
    points.push({ x: 24 + 384 * t, y: 86 + 44 * Math.sin(t * Math.PI * 2) });
    if (i) lengths.push(lengths[i - 1] + Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y));
  }
  const total = lengths[600], step = total / count;
  function at(distance) {
    let i = 1;
    while (i < 600 && lengths[i] < distance) i++;
    const f = (distance - lengths[i - 1]) / (lengths[i] - lengths[i - 1]);
    return `${(points[i - 1].x + f * (points[i].x - points[i - 1].x)).toFixed(2)},${(points[i - 1].y + f * (points[i].y - points[i - 1].y)).toFixed(2)}`;
  }
  return Array.from({length: count}, (_, i) => {
    const gap = Math.min(6, step * 0.24), start = i * step + gap / 2, end = (i + 1) * step - gap / 2;
    return Array.from({length: 25}, (_, k) => `${k ? "L" : "M"}${at(start + (end - start) * k / 24)}`).join(" ");
  });
}

function renderGoalPath(pnl) {
  const el = $("goalPath");
  if (!el) return;
  state.lastGoalPnl = pnl;
  const rawPnl = pnl;
  pnl = (pnl || 0) * state.fxRate;
  const GOAL_TARGET = state.monthlyTarget;
  const frac = pnl / GOAL_TARGET;
  el.setAttribute("aria-label", `Monthly profit ${goalMoney(pnl)} toward ${goalMoney(GOAL_TARGET)}`);
  const completed = Math.max(0, Math.min(state.tradingDays, frac * state.tradingDays));
  const segments = goalPathSegments(state.tradingDays);
  let svg = '<svg viewBox="0 0 480 170" aria-hidden="true" focusable="false">';
  segments.forEach((d, i) => {
    const fill = Math.max(0, Math.min(1, completed - i));
    svg += `<path class="goal-path-segment" d="${d}"/>`;
    if (fill > 0) svg += `<path class="goal-path-fill" data-complete="${fill >= 1 - 1e-9}" d="${d}" pathLength="100" stroke-dasharray="${fill * 100} 100"/>`;
  });
  // Code-native trophy: neutral until the monthly target is reached.
  svg += `<g class="goal-path-trophy${frac >= 1 ? " is-earned" : ""}" transform="translate(430 56)">
    <path d="M8 5 H34 V19 C34 36 8 36 8 19 Z M8 9 H1 V17 Q1 27 12 27 M34 9 H41 V17 Q41 27 30 27 M21 33 V44 M11 49 H31 M15 44 H27"/>
    <text x="21" y="69">GOAL</text></g></svg>`;
  el.innerHTML = svg;
  const finished = Math.min(state.tradingDays, Math.floor(completed + 1e-9));
  $("goalPathCaption").textContent = rawPnl == null
    ? `${state.tradingDays} segments · ${goalMoney(GOAL_TARGET / state.tradingDays)} each`
    : `${finished} of ${state.tradingDays} segments complete · ${goalMoney(GOAL_TARGET / state.tradingDays)} each`;
  el.setAttribute("aria-label", rawPnl == null ? "Monthly target path, awaiting trade data" :
    `${goalMoney(pnl)} of ${goalMoney(GOAL_TARGET)}. ${finished} of ${state.tradingDays} daily target segments complete${frac >= 1 ? ". Trophy earned" : ""}.`);

  const amt = $("goalAmount");
  amt.textContent = fmt.money(rawPnl);
  amt.className = "goal-amount " + signClass(pnl);
  $("goalPct").textContent = `${Math.round(frac * 100)}% of goal`;

  const note = $("goalNote");
  if (rawPnl == null) {
    note.textContent = "Monthly progress will appear when your trades load.";
    $("goalPct").textContent = "—";
  } else if (pnl === 0) {
    note.textContent = `Start with your ${goalMoney(GOAL_TARGET / state.tradingDays)} daily target.`;
  } else if (pnl < 0) {
    note.textContent = "Down month — get back to break even first.";
  } else if (frac >= 1) {
    note.textContent = `Goal smashed — ${goalMoney(pnl - GOAL_TARGET)} over target. 🟢`;
  } else {
    const remain = GOAL_TARGET - pnl;
    const days = Math.max(1, Math.ceil(remain / (GOAL_TARGET / state.tradingDays)));
    note.textContent = `${goalMoney(remain)} to go — ${days} day${days === 1 ? "" : "s"} at your planned daily target.`;
  }


}

/* ---------- The Build (all-time P&L brought to life: foundation → topped out) ---------- */

// The tower rises across this all-time-net range: bare frame at/below FLOOR,
// fully topped out at/above TOP. Breakeven (0) lands a third of the way up —
// the goal is to build out of the hole and top the tower out.
const BUILD_FLOOR = -50000;
const BUILD_TOP = 75000;

const BUILD_STAGES = [
  { t: 0,     name: "Foundation" },
  { t: 5000,  name: "Framing" },
  { t: 15000, name: "Walls Up" },
  { t: 25000, name: "Roof On" },
  { t: 50000, name: "Windows In" },
  { t: 75000, name: "Topped Out" },
];

// Two-layer brick tower: a dashed blueprint outline (always visible) and a
// brick-filled twin, revealed bottom-up by a CSS mask as net climbs. The gold
// roof only fades in once fully topped out.
const BUILD_SVG = `
  <svg class="ki-island ki-red" viewBox="0 0 200 300" preserveAspectRatio="xMidYMid meet">
    <rect x="40" y="60" width="120" height="210" fill="none" stroke="rgba(255,255,255,0.14)" stroke-width="1.5"/>
    <line x1="40" y1="95" x2="160" y2="95" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <line x1="40" y1="130" x2="160" y2="130" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <line x1="40" y1="165" x2="160" y2="165" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <line x1="40" y1="200" x2="160" y2="200" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <line x1="40" y1="235" x2="160" y2="235" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <polygon points="30,60 170,60 100,25" fill="none" stroke="rgba(255,255,255,0.14)" stroke-width="1.5" stroke-dasharray="4 4"/>
    <line x1="10" y1="270" x2="190" y2="270" stroke="rgba(255,255,255,0.2)" stroke-width="2"/>
  </svg>
  <svg class="ki-island ki-green" viewBox="0 0 200 300" preserveAspectRatio="xMidYMid meet">
    <defs>
      <pattern id="brickFill" width="24" height="12" patternUnits="userSpaceOnUse">
        <rect width="24" height="12" fill="#7a3d22"/>
        <rect x="0.5" y="0.5" width="10" height="5" rx="0.6" fill="#c9752f"/>
        <rect x="12.5" y="0.5" width="10" height="5" rx="0.6" fill="#c9752f"/>
        <rect x="6.5" y="6.5" width="10" height="5" rx="0.6" fill="#c9752f"/>
        <rect x="18.5" y="6.5" width="4.5" height="5" rx="0.6" fill="#c9752f"/>
        <rect x="-5.5" y="6.5" width="4.5" height="5" rx="0.6" fill="#c9752f"/>
      </pattern>
    </defs>
    <rect x="40" y="60" width="120" height="210" fill="url(#brickFill)" stroke="rgba(0,0,0,0.35)" stroke-width="1.5"/>
    <rect x="55" y="75" width="16" height="20" rx="2" fill="#0d0f13" opacity="0.85"/>
    <rect x="129" y="75" width="16" height="20" rx="2" fill="#0d0f13" opacity="0.85"/>
    <rect x="55" y="110" width="16" height="20" rx="2" fill="#0d0f13" opacity="0.85"/>
    <rect x="129" y="110" width="16" height="20" rx="2" fill="#0d0f13" opacity="0.85"/>
    <rect x="55" y="145" width="16" height="20" rx="2" fill="#0d0f13" opacity="0.85"/>
    <rect x="129" y="145" width="16" height="20" rx="2" fill="#0d0f13" opacity="0.85"/>
    <rect x="55" y="180" width="16" height="20" rx="2" fill="#f0cf6e" opacity="0.9"/>
    <rect x="129" y="180" width="16" height="20" rx="2" fill="#f0cf6e" opacity="0.9"/>
    <rect x="55" y="215" width="16" height="20" rx="2" fill="#f0cf6e" opacity="0.9"/>
    <rect x="129" y="215" width="16" height="20" rx="2" fill="#f0cf6e" opacity="0.9"/>
    <rect x="80" y="245" width="40" height="25" rx="2" fill="#0d0f13" opacity="0.9"/>
  </svg>
  <svg class="ki-island ki-roof" viewBox="0 0 200 300" preserveAspectRatio="xMidYMid meet">
    <polygon points="30,60 170,60 100,20" fill="#d8b34a"/>
    <polygon points="30,60 170,60 100,20" fill="none" stroke="#0d0f13" stroke-width="1.5"/>
  </svg>
`;

function buildProgress(net) {
  if (net <= BUILD_FLOOR) return 0;
  if (net >= BUILD_TOP) return 1;
  return (net - BUILD_FLOOR) / (BUILD_TOP - BUILD_FLOOR);
}

function renderFarm(net) {
  const stage = $("kingdomStage");
  if (!stage) return;
  net = Number(net) || 0;

  let scene = stage.querySelector(".ki-scene");
  if (!scene) {
    scene = document.createElement("div");
    scene.className = "ki-scene ki-build";
    scene.innerHTML = BUILD_SVG;
    stage.appendChild(scene);
  }

  // The tower fills from the ground up as net climbs FLOOR → TOP.
  const progress = buildProgress(net);
  const tide = progress * 100;
  const green = scene.querySelector(".ki-green");
  let mask;
  if (progress <= 0) {
    mask = "linear-gradient(rgba(0,0,0,0), rgba(0,0,0,0))";
  } else if (progress >= 1) {
    mask = "linear-gradient(#000, #000)";
  } else {
    mask = `linear-gradient(to top, #000 ${Math.max(0, tide - 10).toFixed(1)}%, `
      + `rgba(0,0,0,0) ${Math.min(100, tide + 4).toFixed(1)}%)`;
  }
  green.style.webkitMaskImage = mask;
  green.style.maskImage = mask;

  const roof = scene.querySelector(".ki-roof");
  if (roof) roof.style.opacity = progress >= 1 ? "1" : "0";

  // ── Side panel ──
  const netEl = $("kingdomNet");
  netEl.textContent = fmt.money(net);
  netEl.className = "kingdom-net " + signClass(net);

  const unlocked = BUILD_STAGES.filter(m => net >= m.t);
  $("kingdomRank").textContent =
    net < 0 ? "Excavating" : (unlocked.length ? unlocked[unlocked.length - 1].name : "Cleared Site");

  const next = BUILD_STAGES.find(m => m.t > net);
  const barFill = $("kingdomBarFill");
  if (net < 0) {
    const rec = Math.max(0, Math.min(1, (net - BUILD_FLOOR) / (0 - BUILD_FLOOR)));
    barFill.style.width = (rec * 100).toFixed(1) + "%";
    $("kingdomNextLabel").textContent = "Back to ground level";
    $("kingdomNextPct").textContent = Math.round(rec * 100) + "%";
    $("kingdomNextGoal").textContent = `Fill ${fmt.money(-net, { sign: false })} to break even`;
    $("kingdomSub").textContent = "Below ground — trade it back to level";
  } else if (!next) {
    barFill.style.width = "100%";
    $("kingdomNextLabel").textContent = "Build complete";
    $("kingdomNextPct").textContent = "100%";
    $("kingdomNextGoal").textContent = "🏗️ Topped out";
    $("kingdomSub").textContent = "Fully built — the whole tower stands";
  } else {
    const prev = [...BUILD_STAGES].reverse().find(m => m.t <= net)?.t ?? 0;
    const segFrac = Math.max(0, Math.min(1, (net - prev) / (next.t - prev)));
    barFill.style.width = (segFrac * 100).toFixed(1) + "%";
    $("kingdomNextLabel").textContent = "Next";
    $("kingdomNextPct").textContent = Math.round(segFrac * 100) + "%";
    $("kingdomNextGoal").textContent = `${fmt.money(next.t - net, { sign: false })} to ${next.name}`;
    $("kingdomSub").textContent = "Build it up with clean profit";
  }

  $("kingdomMilestones").innerHTML = BUILD_STAGES.map(m => {
    const cls = net >= m.t ? "unlocked" : (m === next ? "target" : "");
    return `<span class="km-chip ${cls}"><span class="km-ico" aria-hidden="true"></span>${m.name} · ${fmt.money(m.t, { sign: false, compact: true })}</span>`;
  }).join("");
}

function renderStats(s) {
  const setVal = (id, value, { sign = true } = {}) => {
    const el = $(id);
    el.textContent = fmt.money(value, { sign });
    el.classList.remove("pos", "neg", "neutral");
    el.classList.add(signClass(value));
  };
  setVal("netPnl", s.net_pnl);
  setVal("expectancy", s.expectancy);

  $("winRate").textContent = fmt.pct(s.win_rate);
  $("winRate").className = "stat-value " + (s.win_rate >= 50 ? "pos" : s.win_rate > 0 ? "neg" : "neutral");

  $("profitFactor").textContent = s.profit_factor ? Number(s.profit_factor).toFixed(2) : "—";
  $("profitFactor").className = "stat-value " + (s.profit_factor >= 1 ? "pos" : s.profit_factor > 0 ? "neg" : "neutral");

  $("avgWinLoss").innerHTML = `<span class="pos">${fmt.money(s.avg_win)}</span> / <span class="neg">${fmt.money(s.avg_loss)}</span>`;
  $("bestWorst").innerHTML = `<span class="pos">${fmt.money(s.best_trade)}</span> / <span class="neg">${fmt.money(s.worst_trade)}</span>`;

  $("tradeCount").textContent = `${s.trade_count} / ${s.close_count}`;

  const score = s.close_count ? zellaScore(s) : 0;
  $("zellaScore").textContent = score.toFixed(2);
  $("zellaScore").className = "stat-value " + (score >= 60 ? "pos" : score >= 30 ? "neutral" : "neg");
  $("scoreBarFill").style.width = `${Math.min(100, score)}%`;
  $("scoreBarKnob").style.left = `${Math.min(100, score)}%`;
}

/* ---------- recent trades (closes only) ---------- */

function renderRecentTrades(fills) {
  const tbody = document.querySelector("#recentTradesTable tbody");
  tbody.innerHTML = "";
  const closes = fills.filter(f => (f.realized_pnl || 0) !== 0);
  closes.slice(0, 40).forEach(r => {
    const tr = document.createElement("tr");
    const dateStr = fmtDisplayDate((r.trade_date || r.datetime || "").slice(0, 10));
    const timeStr = fmtDisplayTime(r.datetime);
    tr.innerHTML = `
      <td>
        <div class="cell-date">${dateStr}</div>
        <div class="cell-time">${timeStr}</div>
      </td>
      <td class="sym">${formatSymbol(r)}</td>
      <td class="num ${signClass(r.realized_pnl)}">${fmt.money(r.realized_pnl)}</td>`;
    tbody.appendChild(tr);
  });
  if (!closes.length) tbody.innerHTML = `<tr><td colspan="3" class="muted">No closed trades yet.</td></tr>`;
}

async function loadOpenPositions() {
  const tbody = document.querySelector("#recentTradesTable tbody");
  tbody.innerHTML = `<tr><td colspan="3" class="muted">Loading open positions…</td></tr>`;
  try {
    const data = await api("/api/journal/open-positions");
    renderOpenPositions(data.positions || []);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="3" class="muted">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderOpenPositions(positions) {
  const tbody = document.querySelector("#recentTradesTable tbody");
  tbody.innerHTML = "";
  if (!positions.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="muted">No open positions.</td></tr>`;
    return;
  }
  positions.forEach(p => {
    const tr = document.createElement("tr");
    const dateStr = fmtDisplayDate((p.open_date || (p.open_datetime || "").slice(0, 10)));
    const timeStr = fmtDisplayTime(p.open_datetime);
    const qty = p.position_qty ?? "";
    // Build a trade-like object so the existing detail modal works
    const tradeLike = {
      ticker: p.underlying || p.symbol,
      symbol: p.symbol,
      instrument: formatOpenPositionInstrument(p),
      side: p.put_call === "C" ? "CALL" : p.put_call === "P" ? "PUT" : (qty > 0 ? "BUY" : "SELL"),
      put_call: p.put_call,
      asset_class: p.asset_class,
      strike: p.strike,
      expiry: p.expiry,
      multiplier: p.multiplier,
      open_datetime: p.open_datetime,
      close_datetime: null,
      is_open: true,
      fill_count: p.fill_count,
      avg_entry_price: p.avg_entry_price,
      avg_exit_price: null,
      qty_opened: p.position_qty > 0 ? p.position_qty : 0,
      qty_closed: 0,
      position_qty: p.position_qty,
      net_pnl: p.floating_pnl,
      gross_pnl: p.floating_pnl,
      net_after_comm: p.floating_pnl,
      realized_pnl: 0.0,
      commission: 0.0,
      net_roi: null,
      fills: p.fills || [],
    };
    tr.classList.add("cal-clickable");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => openTradeDetail(tradeLike));
    tr.innerHTML = `
      <td>
        <div class="cell-date">${dateStr}</div>
        <div class="cell-time">${timeStr} <span class="muted" style="font-size:10px;">(open)</span></div>
      </td>
      <td class="sym">${formatSymbol({ symbol: p.symbol, underlying: p.underlying, asset_class: p.asset_class, strike: p.strike, expiry: p.expiry, put_call: p.put_call })}</td>
      <td class="num ${signClass(p.floating_pnl)}">${fmt.money(p.floating_pnl)}</td>`;
    tbody.appendChild(tr);
  });
}

function formatOpenPositionInstrument(p) {
  const isOpt = p.asset_class === "OPT" || p.asset_class === "FOP";
  if (isOpt && p.expiry && p.strike != null) {
    const [y, m, d] = String(p.expiry).split("-");
    const strikeNum = Number(p.strike);
    const strikeStr = Number.isInteger(strikeNum) ? String(strikeNum) : strikeNum.toFixed(2).replace(/\.?0+$/, "");
    const pc = p.put_call === "P" ? "PUT" : p.put_call === "C" ? "CALL" : "";
    return `${m}-${d}-${y} ${escapeHtml(strikeStr)} ${pc}`.trim();
  }
  return p.underlying || p.symbol || "";
}

function renderSymbolTable(rows) {
  const tbody = document.querySelector("#symbolTable tbody");
  tbody.innerHTML = "";
  rows.slice(0, 20).forEach(r => {
    const tr = document.createElement("tr");
    const winPct = r.count ? (r.wins / r.count * 100) : 0;
    tr.innerHTML = `
      <td>${escapeHtml(r.symbol)}</td>
      <td class="num ${signClass(r.pnl)}">${fmt.money(r.pnl)}</td>
      <td class="num">${r.count}</td>
      <td class="num">${fmt.pct(winPct)}</td>`;
    tbody.appendChild(tr);
  });
  if (!rows.length) tbody.innerHTML = `<tr><td colspan="4" class="muted">No closed trades yet.</td></tr>`;
}

function renderDayTable(rows) {
  const tbody = document.querySelector("#dayTable tbody");
  tbody.innerHTML = "";
  rows.slice().reverse().slice(0, 30).forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(r.date)}</td><td class="num ${signClass(r.pnl)}">${fmt.money(r.pnl)}</td>`;
    tbody.appendChild(tr);
  });
  if (!rows.length) tbody.innerHTML = `<tr><td colspan="2" class="muted">No days yet.</td></tr>`;
}

function renderFills(rows) {
  const tbody = document.querySelector("#fillsTable tbody");
  tbody.innerHTML = "";
  rows.forEach(r => {
    const tr = document.createElement("tr");
    const dt = r.datetime
      ? `${fmtDisplayDate(r.datetime.slice(0, 10))} ${fmtDisplayTime(r.datetime, false)}`
      : (r.trade_date ? fmtDisplayDate(r.trade_date) : "");
    tr.innerHTML = `
      <td>${dt}</td>
      <td class="sym">${formatSymbol(r)}</td>
      <td>${escapeHtml(r.asset_class || "")}</td>
      <td>${escapeHtml(r.buy_sell || "")}</td>
      <td class="num">${fmt.num(r.quantity, 0)}</td>
      <td class="num">${fmt.num(r.trade_price, 4)}</td>
      <td class="num">${fmt.money(r.proceeds, { sign: false })}</td>
      <td class="num">${fmt.money(r.commission, { sign: false })}</td>
      <td class="num ${signClass(r.realized_pnl)}">${r.realized_pnl ? fmt.money(r.realized_pnl) : "—"}</td>
      <td>${escapeHtml(r.open_close || "")}</td>`;
    tbody.appendChild(tr);
  });
  $("fillsSub").textContent = `${rows.length} fills shown`;
  if (!rows.length) tbody.innerHTML = `<tr><td colspan="10" class="muted">No fills to show.</td></tr>`;
}

/* Self-reported discipline awards, independent of P&L. */
function validRulesDate(date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || "")) return false;
  const d = new Date(`${date}T12:00:00Z`), now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === date && date <= today;
}
function followedRules(date) {
  if (!validRulesDate(date)) return false;
  const key = `journal_rules_${date}`;
  if (_supabase) return _journalProfile?.enabled ? _journalProfile.rules?.[date] === true : _session?.user?.user_metadata?.[key] === true;
  try { return localStorage.getItem(key) === "true"; } catch (_) { return false; }
}
function renderRuleStars() {
  document.querySelectorAll("[data-rule-date]").forEach(star => { star.hidden = !followedRules(star.dataset.ruleDate); });
  const button = $("dayRulesButton");
  if (!button) return;
  const earned = followedRules(state.rulesDate);
  button.setAttribute("aria-pressed", String(earned));
  button.textContent = earned ? "★ Rules followed · undo" : "☆ I followed my rules";
  button.disabled = state.rulesSaving || !validRulesDate(state.rulesDate) || Boolean(_supabase && !_session);
}
async function toggleDayRules() {
  const date = state.rulesDate, userId = _session?.user?.id;
  if (state.rulesSaving || !validRulesDate(date) || (_supabase && !userId)) return;
  const earned = !followedRules(date), key = `journal_rules_${date}`;
  state.rulesSaving = true;
  $("dayRulesStatus").textContent = "Saving…";
  renderRuleStars();
  try {
    if (_supabase) {
      if (_profileError) throw new Error("Could not load your daily reviews. Refresh and retry.");
      if (_journalProfile?.enabled) {
        await api("/api/journal/profile", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({kind:"rules",day:date,followed:earned})});
        if (_session?.user?.id !== userId) return;
        _journalProfile.rules[date] = earned;
      } else {
        const { error } = await _supabase.auth.updateUser({ data: { [key]: earned } });
        if (error) throw error;
        if (_session?.user?.id !== userId) return;
        _session.user.user_metadata = { ..._session.user.user_metadata, [key]: earned };
      }
    } else { localStorage.setItem(key, String(earned)); }
    if (state.rulesDate === date && _session?.user?.id === userId) $("dayRulesStatus").textContent = earned
      ? (_supabase ? "Gold star saved to your account." : "Gold star saved in this browser.") : "Gold star removed.";
  } catch (error) {
    if (state.rulesDate === date && _session?.user?.id === userId) $("dayRulesStatus").textContent = `Not saved: ${error.message}`;
  } finally { state.rulesSaving = false; renderRuleStars(); }
}

/* ---------- calendar ---------- */

function renderCalendar(data) {
  $("calendarTitle").textContent = `${data.month_name} ${data.year}`;
  const chip = $("calMonthPnl");
  chip.textContent = fmt.money(data.month_pnl, { compact: true });
  chip.className = "cal-stat-chip " + signClass(data.month_pnl);
  $("calActiveDays").textContent = `${data.active_days} day${data.active_days === 1 ? "" : "s"}`;

  const grid = $("calendarGrid");
  grid.innerHTML = "";

  // Row 1: weekday headers (cols 1-7) + a blank cell in col 8 above the week
  // summary column so everything lines up.
  ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].forEach(label => {
    const el = document.createElement("div");
    el.className = "cal-weekday";
    el.textContent = label;
    grid.appendChild(el);
  });
  const spacer = document.createElement("div");
  spacer.className = "cal-weekday cal-week-spacer";
  grid.appendChild(spacer);

  // Pre-compute each calendar-row's Sunday ISO date so week cards are clickable.
  // Row 0's Sunday = (first of month) - lead_blank days.
  const weekStartsAt = [];
  const firstOfMonth = new Date(data.year, data.month - 1, 1);
  for (let wi = 0; wi < (data.weeks || []).length; wi++) {
    const sunday = new Date(firstOfMonth);
    sunday.setDate(firstOfMonth.getDate() - data.lead_blank + wi * 7);
    const y = sunday.getFullYear();
    const m = String(sunday.getMonth() + 1).padStart(2, "0");
    const d = String(sunday.getDate()).padStart(2, "0");
    weekStartsAt.push(`${y}-${m}-${d}`);
  }

  let weekIndex = 0;
  const appendWeekCard = () => {
    const w = data.weeks[weekIndex] || { pnl: 0, active_days: 0 };
    const startIso = weekStartsAt[weekIndex];
    const card = document.createElement("div");
    card.className = "week-card " + (w.active_days ? signClass(w.pnl) : "empty");
    if (startIso) {
      card.classList.add("clickable");
      card.addEventListener("click", () => openWeekModal(startIso));
    }
    card.innerHTML = `
      <div class="week-title">Week ${weekIndex + 1}</div>
      <div class="week-pnl">${w.active_days ? fmt.money(w.pnl, { compact: true }) : fmt.money(0, { compact: true })}</div>
      <div class="week-sub">${w.active_days} day${w.active_days === 1 ? "" : "s"}</div>`;
    grid.appendChild(card);
    weekIndex++;
  };

  const appendBlank = () => {
    const pad = document.createElement("div");
    pad.className = "cal-cell cal-cell-blank";
    grid.appendChild(pad);
  };

  let dayColIndex = 0;
  const maybeCloseRow = () => {
    if (dayColIndex === 7) { appendWeekCard(); dayColIndex = 0; }
  };

  for (let i = 0; i < data.lead_blank; i++) {
    appendBlank();
    dayColIndex++;
    maybeCloseRow();
  }

  data.days.forEach(d => {
    const cell = document.createElement("div");
    cell.className = "cal-cell";
    if (d.trades > 0) {
      cell.classList.add(d.pnl > 0 ? "cal-pos" : d.pnl < 0 ? "cal-neg" : "cal-neutral");
    }
    if (validRulesDate(d.date)) {
      cell.classList.add("cal-clickable");
      cell.tabIndex = 0;
      cell.setAttribute("role", "button");
      cell.setAttribute("aria-label", `Review ${d.date}`);
      cell.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); cell.click(); }
      });
      cell.addEventListener("click", () => {
        if (state.viewMode === "week") {
          openWeekModal(weekStartFor(d.date));
        } else {
          openDayModal(d.date);
        }
      });
    }
    const pnlLine = d.trades > 0
      ? `<div class="cal-cell-pnl ${signClass(d.pnl)}">${fmt.money(d.pnl, { compact: true })}</div>
         <div class="cal-cell-sub">${d.trades} trade${d.trades === 1 ? "" : "s"}</div>
         <div class="cal-cell-sub">${fmt.pct(d.win_rate)}</div>`
      : "";
    cell.innerHTML = `<div class="cal-cell-day">${escapeHtml(d.day)}</div>${pnlLine}`;
    const star = document.createElement("span");
    star.className = "cal-rule-star";
    star.dataset.ruleDate = d.date;
    star.textContent = "★";
    star.setAttribute("role", "img");
    star.setAttribute("aria-label", "Followed my rules");
    star.title = "Followed my rules";
    star.hidden = !followedRules(d.date);
    cell.querySelector(".cal-cell-day").appendChild(star);
    grid.appendChild(cell);
    dayColIndex++;
    maybeCloseRow();
  });

  // Trailing blanks to complete the final row, then its week card.
  if (dayColIndex > 0) {
    while (dayColIndex < 7) { appendBlank(); dayColIndex++; }
    appendWeekCard();
    dayColIndex = 0;
  }

  // If the month has a 6th week that's entirely padding, still render it so
  // the week-card column runs the full month height.
  while (weekIndex < data.weeks.length) {
    for (let i = 0; i < 7; i++) appendBlank();
    appendWeekCard();
  }
}

/* ---------- day-detail modal ---------- */

async function openDayModal(dateIso) {
  const request = ++state.dayRequest, userId = _session?.user?.id;
  state.rulesDate = dateIso;
  $("dayRulesStatus").textContent = "";
  renderRuleStars();
  $("dayModalTitle").textContent = dateIso;
  const modal = $("dayModal");
  const body = document.querySelector("#dayModalTable tbody");
  body.innerHTML = `<tr><td colspan="6" class="muted">Loading…</td></tr>`;
  modal.hidden = false;
  document.body.style.overflow = "hidden";

  try {
    const d = await api(`/api/journal/day?date=${encodeURIComponent(dateIso)}`);
    if (request !== state.dayRequest || _session?.user?.id !== userId) return;
    const dateObj = new Date(dateIso + "T00:00:00");
    const heading = dateObj.toLocaleDateString(undefined, {
      weekday: "short", year: "numeric", month: "short", day: "2-digit",
    });
    $("dayModalTitle").textContent = heading;
    const pnlEl = $("dayModalPnl");
    pnlEl.textContent = fmt.money(d.net_pnl);
    pnlEl.className = signClass(d.net_pnl);

    $("dayModalTotal").textContent = d.total_trades;
    $("dayModalGross").textContent = fmt.money(d.gross_pnl);
    $("dayModalGross").className = "stat-value " + signClass(d.gross_pnl);
    $("dayModalWL").textContent = `${d.wins} / ${d.losses}`;
    $("dayModalComm").textContent = fmt.money(d.commissions, { sign: false });
    $("dayModalWinRate").textContent = fmt.pct(d.win_rate);
    $("dayModalVolume").textContent = fmt.num(d.volume, 0);
    $("dayModalPF").textContent = d.profit_factor ? Number(d.profit_factor).toFixed(2) : "—";

    drawIntraday(d.intraday);
    renderDayTrades(d.trades);
  } catch (err) {
    if (request !== state.dayRequest || _session?.user?.id !== userId) return;
    body.innerHTML = `<tr><td colspan="6" class="muted">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function closeDayModal() {
  state.dayRequest++;
  state.rulesDate = null;
  $("dayModal").hidden = true;
  document.body.style.overflow = "";
}

/* ---------- week-detail modal ---------- */

function weekStartFor(dateIso) {
  // Sun-anchored week start (matches backend/calendar)
  const d = new Date(dateIso + "T00:00:00");
  const daysBack = d.getDay(); // Sun=0..Sat=6
  d.setDate(d.getDate() - daysBack);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function openWeekModal(startIso) {
  const modal = $("weekModal");
  const body = document.querySelector("#weekModalTable tbody");
  body.innerHTML = `<tr><td colspan="7" class="muted">Loading…</td></tr>`;
  modal.hidden = false;
  document.body.style.overflow = "hidden";

  try {
    const w = await api(`/api/journal/week?start=${encodeURIComponent(startIso)}`);
    const startObj = new Date(startIso + "T00:00:00");
    const endObj = new Date(w.end + "T00:00:00");
    const sameMonth = startObj.getMonth() === endObj.getMonth();
    const startLabel = startObj.toLocaleDateString(undefined,
      { month: "short", day: "2-digit" });
    const endLabel = endObj.toLocaleDateString(undefined,
      sameMonth ? { day: "2-digit", year: "numeric" }
                : { month: "short", day: "2-digit", year: "numeric" });
    $("weekModalTitle").textContent = `${startLabel} – ${endLabel}`;

    const pnlEl = $("weekModalPnl");
    pnlEl.textContent = fmt.money(w.net_pnl);
    pnlEl.className = signClass(w.net_pnl);

    $("weekModalTotal").textContent = w.total_trades;
    const gross = $("weekModalGross");
    gross.textContent = fmt.money(w.gross_pnl);
    gross.className = "stat-value " + signClass(w.gross_pnl);
    $("weekModalWL").textContent = `${w.wins} / ${w.losses}`;
    $("weekModalComm").textContent = fmt.money(w.commissions, { sign: false });
    $("weekModalWinRate").textContent = fmt.pct(w.win_rate);
    $("weekModalVolume").textContent = fmt.num(w.volume, 0);
    $("weekModalPF").textContent = w.profit_factor ? Number(w.profit_factor).toFixed(2) : "—";

    renderWeekDayStrip(w.days);
    drawWeekBars(w.days);
    renderZellaScale(w);
    renderWeekTrades(w.days, w.trades);
  } catch (err) {
    body.innerHTML = `<tr><td colspan="7" class="muted">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function closeWeekModal() {
  $("weekModal").hidden = true;
  // Only release scroll lock if no other modal is on top
  if ($("tradeDetailModal").hidden && $("dayModal").hidden && $("settingsModal").hidden) {
    document.body.style.overflow = "";
  }
}

function renderWeekDayStrip(days) {
  const strip = $("weekDayStrip");
  strip.innerHTML = "";
  days.forEach(d => {
    const card = document.createElement("div");
    const cls = d.trades > 0 ? (d.pnl > 0 ? "pos" : d.pnl < 0 ? "neg" : "") : "empty";
    card.className = `week-day-card ${cls}`;
    card.innerHTML = `
      <div class="wd-label">${escapeHtml(d.weekday)} ${escapeHtml(d.day)}</div>
      <div class="wd-pnl ${d.trades ? signClass(d.pnl) : "muted"}">${d.trades ? fmt.money(d.pnl, { compact: true }) : "—"}</div>
      <div class="wd-sub">${d.trades ? `${d.trades} trade${d.trades === 1 ? "" : "s"}` : ""}</div>`;
    if (validRulesDate(d.date)) {
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", `Review ${d.date}`);
      card.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); card.click(); }
      });
      card.style.cursor = "pointer";
      card.addEventListener("click", () => {
        closeWeekModal();
        openDayModal(d.date);
      });
    }
    strip.appendChild(card);
  });
}

function drawWeekBars(days) {
  const canvas = $("weekModalChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 480;
  const h = canvas.clientHeight || 120;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const styles = getComputedStyle(document.body);
  const axisColor = styles.getPropertyValue("--chart-axis").trim() || "rgba(255,255,255,0.45)";
  const zeroColor = styles.getPropertyValue("--chart-zero").trim() || "rgba(255,255,255,0.22)";
  const greenColor = styles.getPropertyValue("--green").trim() || "#10b981";
  const redColor = styles.getPropertyValue("--red").trim() || "#ef4444";

  const pad = { top: 10, right: 10, bottom: 22, left: 30 };
  const innerW = w - pad.left - pad.right;
  const innerH = h - pad.top - pad.bottom;

  const max = Math.max(1, ...days.map(d => Math.abs(d.pnl)));
  const zeroY = pad.top + innerH / 2;

  ctx.strokeStyle = zeroColor;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, zeroY);
  ctx.lineTo(pad.left + innerW, zeroY);
  ctx.stroke();

  const barW = innerW / days.length * 0.55;
  const slotW = innerW / days.length;
  ctx.fillStyle = axisColor;
  ctx.font = "11px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";

  days.forEach((d, i) => {
    const cx = pad.left + slotW * (i + 0.5);
    const yScale = (Math.abs(d.pnl) / max) * (innerH / 2 - 2);
    if (d.pnl >= 0) {
      ctx.fillStyle = greenColor;
      ctx.fillRect(cx - barW / 2, zeroY - yScale, barW, yScale);
    } else {
      ctx.fillStyle = redColor;
      ctx.fillRect(cx - barW / 2, zeroY, barW, yScale);
    }
    ctx.fillStyle = axisColor;
    ctx.fillText(d.weekday, cx, h - 6);
  });
}

function renderZellaScale(w) {
  $("weekMaxLoss").textContent = w.max_loss ? fmt.money(w.max_loss) : fmt.money(0);
  $("weekMaxProfit").textContent = w.max_profit ? fmt.money(w.max_profit) : fmt.money(0);
  const range = Math.max(1, Math.abs(w.max_profit) + Math.abs(w.max_loss));
  const balancePoint = (Math.abs(w.max_loss) + w.net_pnl) / range * 100;
  const clamped = Math.max(0, Math.min(100, balancePoint));
  $("weekScaleFill").style.left = `${clamped}%`;
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
const RULE_LABELS = {
  "ADDED-DOWN": "Added to a losing position",
  "OVERSIZED": "Position over $4,000 cap",
  "STOP-BLOWN": "Loss ran past the -25% stop",
  "OVERNIGHT": "Held overnight — not closed same session",
  "OPEN-CHASE": "Entered in the first 15 minutes",
};
function ruleBadges(t) {
  const flags = (t && t.rule_flags) || [];
  if (!flags.length) return "";
  return " " + flags.map(f =>
    `<span class="rule-badge" title="${escapeHtml(RULE_LABELS[f] || f)}">${escapeHtml(f)}</span>`
  ).join("");
}

function renderWeekTrades(days, trades) {
  const tbody = document.querySelector("#weekModalTable tbody");
  tbody.innerHTML = "";
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No closed trades this week.</td></tr>`;
    return;
  }
  const weekdayByDate = new Map(days.map(d => [d.date, `${escapeHtml(d.weekday)} ${escapeHtml(d.day)}`]));
  trades.forEach(t => {
    const tr = document.createElement("tr");
    const sideClass = t.side === "C" || t.side === "CALL" || t.side === "BUY" ? "side-call" :
                      t.side === "P" || t.side === "PUT" || t.side === "SELL" ? "side-put" : "";
    const sideLabel = t.side === "C" ? "CALL" : t.side === "P" ? "PUT" : t.side;
    const roi = t.net_roi != null ? (t.net_roi >= 0 ? `${t.net_roi.toFixed(2)}%` : `(${Math.abs(t.net_roi).toFixed(2)}%)`) : "—";
    const dayLabel = weekdayByDate.get(t.trade_date) || "";
    tr.classList.add("cal-clickable");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => {
      closeWeekModal();
      openTradeDetail(t);
    });
    tr.innerHTML = `
      <td class="week-cell-day">${escapeHtml(dayLabel)}</td>
      <td>${escapeHtml(t.time || "")}</td>
      <td><span class="ticker-pill">${escapeHtml(t.ticker || "")}</span></td>
      <td class="${sideClass}">${escapeHtml(sideLabel || "")}</td>
      <td>${escapeHtml(t.instrument || "")}${ruleBadges(t)}</td>
      <td class="num ${signClass(t.net_pnl)}">${fmt.money(t.net_pnl)}</td>
      <td class="num ${signClass(t.net_roi)}">${roi}</td>`;
    tbody.appendChild(tr);
  });
}

function renderDayTrades(trades) {
  const tbody = document.querySelector("#dayModalTable tbody");
  tbody.innerHTML = "";
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted">No closed trades on this day.</td></tr>`;
    return;
  }
  trades.forEach(t => {
    const tr = document.createElement("tr");
    const sideClass = t.side === "C" || t.side === "CALL" || t.side === "BUY" ? "side-call" :
                      t.side === "P" || t.side === "PUT" || t.side === "SELL" ? "side-put" : "";
    const sideLabel = t.side === "C" ? "CALL" : t.side === "P" ? "PUT" : t.side;
    const roi = t.net_roi != null ? (t.net_roi >= 0 ? `${t.net_roi.toFixed(2)}%` : `(${Math.abs(t.net_roi).toFixed(2)}%)`) : "—";
    const openTag = t.is_open ? `<span class="muted" style="font-size:11px;margin-left:6px;">(open)</span>` : "";
    const timeCell = `${escapeHtml(t.time || "")}${openTag}`;
    tr.classList.add("cal-clickable");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => openTradeDetail(t));
    tr.innerHTML = `
      <td>${timeCell}</td>
      <td><span class="ticker-pill">${escapeHtml(t.ticker || "")}</span></td>
      <td class="${sideClass}">${escapeHtml(sideLabel || "")}</td>
      <td>${escapeHtml(t.instrument || "")}${ruleBadges(t)}</td>
      <td class="num ${signClass(t.net_pnl)}">${fmt.money(t.net_pnl)}</td>
      <td class="num ${signClass(t.net_roi)}">${roi}</td>`;
    tbody.appendChild(tr);
  });
}

/* ---------- trade-detail modal ---------- */

const TRADE_CHART_INTERVALS = Object.freeze({
  "1min": { label: "1-minute", seconds: 60, tradingView: "1" },
  "5min": { label: "5-minute", seconds: 300, tradingView: "5" },
  "15min": { label: "15-minute", seconds: 900, tradingView: "15" },
  "30min": { label: "30-minute", seconds: 1800, tradingView: "30" },
  "60min": { label: "1-hour", seconds: 3600, tradingView: "60" },
});

function tradeChartConfig(interval) {
  return TRADE_CHART_INTERVALS[interval] || TRADE_CHART_INTERVALS["5min"];
}

function storedTradeChartInterval() {
  try {
    const interval = localStorage.getItem("journal_chart_interval");
    return TRADE_CHART_INTERVALS[interval] ? interval : "5min";
  } catch (_) {
    return "5min";
  }
}

function openTradeDetail(trade) {
  const modal = $("tradeDetailModal");
  const isOpt = trade.asset_class === "OPT" || trade.asset_class === "FOP";

  $("tradeDetailTicker").textContent = trade.ticker || "";
  $("tradeDetailInstrument").innerHTML =
    escapeHtml(trade.instrument || trade.symbol || "") + ruleBadges(trade);
  $("tradeDetailDate").textContent = trade.close_datetime
    ? new Date(trade.close_datetime.slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, {
        weekday: "short", year: "numeric", month: "short", day: "2-digit",
      })
    : trade.open_datetime
      ? new Date(trade.open_datetime.slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, {
          weekday: "short", year: "numeric", month: "short", day: "2-digit",
        })
      : "";

  const pnlEl = $("tradeDetailPnl");
  pnlEl.textContent = fmt.money(trade.net_pnl);
  pnlEl.className = signClass(trade.net_pnl);

  const sideBadge = $("tradeDetailSideBadge");
  sideBadge.textContent = isOpt ? (trade.put_call === "C" ? "CALL" : trade.put_call === "P" ? "PUT" : trade.side) : trade.side;
  sideBadge.className = "side-badge " + (trade.put_call === "C" ? "is-call" : trade.put_call === "P" ? "is-put" : "");

  const openBadge = $("tradeDetailOpenBadge");
  openBadge.hidden = !trade.is_open;

  // Option metadata rows — visible only for options
  const rightRow = $("tdRightRow");
  const strikeRow = $("tdStrikeRow");
  const expiryRow = $("tdExpiryRow");
  if (isOpt) {
    const pc = trade.put_call === "C" ? "CALL" : trade.put_call === "P" ? "PUT" : "—";
    $("tdRight").textContent = pc;
    if (trade.strike != null) {
      const sn = Number(trade.strike);
      $("tdStrike").textContent = "$" + (Number.isInteger(sn) ? String(sn) : sn.toFixed(2).replace(/\.?0+$/, ""));
    } else {
      $("tdStrike").textContent = "—";
    }
    if (trade.expiry) {
      const [y, m, d] = String(trade.expiry).split("-");
      $("tdExpiry").textContent = `${m}-${d}-${y}`;
    } else {
      $("tdExpiry").textContent = "—";
    }
    rightRow.hidden = false;
    strikeRow.hidden = false;
    expiryRow.hidden = false;
  } else {
    rightRow.hidden = true;
    strikeRow.hidden = true;
    expiryRow.hidden = true;
  }

  // Stat rows
  $("tdSide").textContent = sideBadge.textContent;
  $("tdEntry").textContent = fmtDisplayDateTime(trade.open_datetime) || "—";
  $("tdExit").textContent = trade.is_open ? "—" : (fmtDisplayDateTime(trade.close_datetime) || "—");
  $("tdQtyOpen").textContent = trade.qty_opened != null ? fmt.num(trade.qty_opened, 0) : "—";
  $("tdQtyClose").textContent = trade.qty_closed != null ? fmt.num(trade.qty_closed, 0) : "—";
  $("tdAvgEntry").textContent = trade.avg_entry_price != null ? fmt.money(trade.avg_entry_price, { compact: false, sign: false }) : "—";
  $("tdAvgExit").textContent = trade.avg_exit_price != null ? fmt.money(trade.avg_exit_price, { compact: false, sign: false }) : "—";

  // Total premium paid on entry, received on exit. For options the contract
  // multiplier (usually 100) turns per-contract price into per-contract notional.
  const mult = trade.multiplier || (isOpt ? 100 : 1);
  const totalCost = (trade.avg_entry_price != null && trade.qty_opened != null)
    ? trade.avg_entry_price * trade.qty_opened * mult : null;
  const totalProceeds = (trade.avg_exit_price != null && trade.qty_closed != null && !trade.is_open)
    ? trade.avg_exit_price * trade.qty_closed * mult : null;
  $("tdTotalCost").textContent = totalCost != null
    ? fmt.money(totalCost, { compact: false, sign: false }) : "—";
  $("tdTotalProceeds").textContent = totalProceeds != null
    ? fmt.money(totalProceeds, { compact: false, sign: false }) : "—";
  const gross = $("tdGross");
  gross.textContent = fmt.money(trade.gross_pnl);
  gross.className = signClass(trade.gross_pnl);
  $("tdComm").textContent = fmt.money(trade.commission, { sign: false });
  const net = $("tdNet");
  net.textContent = fmt.money(trade.net_pnl);
  net.className = signClass(trade.net_pnl);
  const roi = $("tdRoi");
  roi.textContent = trade.net_roi != null
    ? (trade.net_roi >= 0 ? `${trade.net_roi.toFixed(2)}%` : `(${Math.abs(trade.net_roi).toFixed(2)}%)`)
    : "—";
  roi.className = signClass(trade.net_roi);
  $("tdFillCount").textContent = trade.fill_count ?? (trade.fills ? trade.fills.length : "—");

  // Fills table
  const tbody = $("tradeDetailFillsBody");
  tbody.innerHTML = "";
  (trade.fills || []).forEach(f => {
    const tr = document.createElement("tr");
    const sideLabel = f.buy_sell || (f.quantity > 0 ? "BUY" : "SELL");
    const sideCls = sideLabel === "BUY" ? "side-call" : "side-put";
    tr.innerHTML = `
      <td>${fmtDisplayTime(f.datetime)}</td>
      <td class="${sideCls}">${sideLabel}</td>
      <td class="num">${fmt.num(f.quantity, 0)}</td>
      <td class="num">${f.trade_price != null ? fmt.num(f.trade_price, 2) : "—"}</td>
      <td class="num">${f.proceeds != null ? fmt.num(f.proceeds, 2) : "—"}</td>
      <td class="num">${fmt.num(f.commission || 0, 2)}</td>
      <td class="num ${signClass(f.realized_pnl)}">${f.realized_pnl != null ? fmt.num(f.realized_pnl, 2) : "—"}</td>`;
    tbody.appendChild(tr);
  });
  if (!(trade.fills || []).length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No fill detail available.</td></tr>`;
  }

  // Chart with entry/exit markers for the underlying
  const chartWrap = $("tradeDetailChartWrap");
  const underlying = (trade.ticker || trade.symbol || "").trim();
  if (underlying) {
    loadTradeChart(chartWrap, underlying, trade);
  } else {
    disposeTradeChart(chartWrap);
  }

  // Notes: load existing note for this trade
  loadTradeNote(trade);

  modal.hidden = false;
  document.body.style.overflow = "hidden";
}

/* ---------- trade notes ---------- */

function tradeNoteKey(trade) {
  const symbol = trade.symbol || trade.ticker;
  const closeDt = trade.close_datetime;
  if (!symbol || !closeDt) return null;
  return { symbol, close_datetime: closeDt, trade_date: (closeDt || "").slice(0, 10) };
}

async function loadTradeNote(trade) {
  const textarea = $("tradeDetailNotes");
  const status = $("tradeDetailNotesStatus");
  const key = tradeNoteKey(trade);
  state.activeNoteKey = key;
  if (state.noteSaveTimer) { clearTimeout(state.noteSaveTimer); state.noteSaveTimer = null; }

  if (!key) {
    textarea.value = "";
    textarea.disabled = true;
    status.textContent = trade.is_open ? "Notes available once the trade closes" : "Note unavailable";
    return;
  }

  textarea.value = "";
  textarea.disabled = true;
  status.textContent = "Loading…";
  try {
    const qs = `symbol=${encodeURIComponent(key.symbol)}&close_datetime=${encodeURIComponent(key.close_datetime)}`;
    const n = await api(`/api/journal/trade-note?${qs}`);
    // Guard against stale responses if the user clicked a different trade
    if (state.activeNoteKey !== key) return;
    textarea.value = n.body || "";
    textarea.disabled = false;
    status.textContent = n.updated_at ? `Saved · ${new Date(n.updated_at).toLocaleString()}` : "";
  } catch (err) {
    status.textContent = `Error: ${escapeHtml(err.message)}`;
    textarea.disabled = false;
  }
}

function scheduleNoteSave() {
  if (state.noteSaveTimer) clearTimeout(state.noteSaveTimer);
  $("tradeDetailNotesStatus").textContent = "Saving…";
  state.noteSaveTimer = setTimeout(saveTradeNote, 600);
}

async function saveTradeNote() {
  const key = state.activeNoteKey;
  if (!key) return;
  const body = $("tradeDetailNotes").value;
  const status = $("tradeDetailNotesStatus");
  try {
    const r = await api("/api/journal/trade-note", {
      method: "POST",
      body: JSON.stringify({ ...key, body }),
    });
    if (state.activeNoteKey !== key) return;
    status.textContent = r.updated_at
      ? `Saved · ${new Date(r.updated_at).toLocaleString()}`
      : body.trim() ? "Saved" : "";
  } catch (err) {
    status.textContent = `Error: ${escapeHtml(err.message)}`;
  }
}

function disposeTradeChart(container) {
  container._chartRequest = (container._chartRequest || 0) + 1;
  if (container._lwObserver) container._lwObserver.disconnect();
  if (container._lwChart) container._lwChart.remove();
  container._lwObserver = container._lwChart = null;
  container.innerHTML = "";
}

function tradeTimestamp(iso) {
  if (!iso) return NaN;
  if (/(Z|[+-]\d{2}:?\d{2})$/i.test(iso)) return Date.parse(iso) / 1000;
  const parts = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
  return parts ? _nyWallClockToUtcMillis(...parts.slice(1).map(Number)) / 1000 : NaN;
}

function tradeChartEvents(trade) {
  const fills = (trade.fills || []).filter(f => Number.isFinite(tradeTimestamp(f.datetime)))
    .slice().sort((a, b) => tradeTimestamp(a.datetime) - tradeTimestamp(b.datetime));
  // Calls and puts can both be bought or sold. Infer direction from the
  // opening execution, never from the option right.
  const first = fills.find(f => String(f.open_close || "").toUpperCase() === "O") || fills[0];
  const buy = f => f.buy_sell ? String(f.buy_sell).toUpperCase() === "BUY" : Number(f.quantity) > 0;
  const openingBuy = first ? buy(first) : !["SELL", "SHORT"].includes(String(trade.side).toUpperCase());
  if (fills.length) return fills.map(f => {
    const oc = String(f.open_close || "").toUpperCase();
    return { time: tradeTimestamp(f.datetime), datetime: f.datetime,
      exit: oc === "C" || (oc !== "O" && buy(f) !== openingBuy),
      quantity: Math.abs(Number(f.quantity)), price: f.trade_price };
  });
  return [
    { datetime: trade.open_datetime, exit: false, quantity: trade.qty_opened, price: trade.avg_entry_price },
    ...(!trade.is_open && trade.close_datetime ? [{ datetime: trade.close_datetime, exit: true,
      quantity: trade.qty_closed, price: trade.avg_exit_price }] : []),
  ].map(e => ({ ...e, time: tradeTimestamp(e.datetime) })).filter(e => Number.isFinite(e.time));
}

function tradeChartMarkers(events, bars, intervalSeconds = 300) {
  return events.flatMap(e => {
    // Attach to the candle containing the execution, not the next candle.
    // Never snap an out-of-session execution to an unrelated bar.
    let lo = 0, hi = bars.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (bars[mid].time <= e.time) lo = mid + 1; else hi = mid;
    }
    const bar = bars[lo - 1];
    if (!bar || e.time >= bar.time + intervalSeconds) return [];
    const qty = e.quantity != null ? ` ${e.quantity}` : "";
    const price = e.price != null ? ` @ $${Number(e.price).toFixed(2)}` : "";
    return [{ time: bar.time, position: e.exit ? "aboveBar" : "belowBar",
      color: e.exit ? "#ef4444" : "#10b981", shape: e.exit ? "arrowDown" : "arrowUp",
      text: `${e.exit ? "Exit" : "Entry"}${qty}${price}` }];
  }).sort((a, b) => a.time - b.time);
}

function appendTradeChartEvents(container, trade) {
  const events = tradeChartEvents(trade);
  const list = document.createElement("div");
  list.className = "trade-chart-events";
  for (const e of events) {
    const item = document.createElement("span");
    item.className = e.exit ? "trade-chart-exit" : "trade-chart-entry";
    const time = new Date(e.time * 1000).toLocaleString("en-GB", {
      timeZone: _DISPLAY_TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    item.textContent = `${e.exit ? "↓ Exit" : "↑ Entry"} · ${time}${e.price != null ? ` · $${Number(e.price).toFixed(2)}` : ""}`;
    list.appendChild(item);
  }
  container.appendChild(list);
}

async function renderTradeChart(container, symbol, trade, interval, request = container._chartRequest) {
  const config = tradeChartConfig(interval);
  container.textContent = `Loading ${symbol} trade chart…`;
  const events = tradeChartEvents(trade);
  const dateFormatter = new Intl.DateTimeFormat("en-CA", { timeZone: _IBKR_TZ,
    year: "numeric", month: "2-digit", day: "2-digit" });
  const dates = [...new Set(events.map(e => dateFormatter.format(new Date(e.time * 1000))))];
  if (!dates.length) throw new Error("No execution dates available");
  const results = await Promise.all(dates.map(date =>
    api(`/api/journal/bars?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}&interval=${encodeURIComponent(interval)}`)
      .catch(() => ({ bars: [] }))));
  if (container._chartRequest !== request) return;
  const bars = [...new Map(results.flatMap(d => d.bars || []).map(b => [b.time, b])).values()]
    .sort((a, b) => a.time - b.time);
  if (!bars.length) throw new Error("Historical intraday data unavailable");
  if (!window.LightweightCharts) throw new Error("Chart library unavailable");

  container.innerHTML = "";
  const caption = document.createElement("div");
  caption.className = "trade-chart-caption";
  caption.textContent = `${symbol} underlying · ${config.label} candles · London/Lisbon time. Arrows mark execution candles; labels show fill prices in USD. Sessions with executions shown.`;
  container.appendChild(caption);
  const plot = document.createElement("div");
  container.appendChild(plot);
  const isLight = document.body.classList.contains("is-light");
  const clock = t => new Date(t * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit", timeZone: _DISPLAY_TZ, hourCycle: "h23" });
  const chart = LightweightCharts.createChart(plot, {
    width: container.clientWidth, height: 340,
    layout: { background: { type: "solid", color: isLight ? "#ffffff" : "#0f1220" },
      textColor: isLight ? "#1f2937" : "#e8e8f0" },
    grid: {
      vertLines: { color: isLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.04)" },
      horzLines: { color: isLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.04)" },
    },
    rightPriceScale: { scaleMargins: { top: 0.2, bottom: 0.2 } },
    timeScale: { timeVisible: true, secondsVisible: false,
      tickMarkFormatter: (t, type) => type <= 2
        ? new Date(t * 1000).toLocaleDateString("en-GB", { timeZone: _DISPLAY_TZ, day: "2-digit", month: "short" }) : clock(t) },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    localization: { timeFormatter: t => new Date(t * 1000).toLocaleString("en-GB", {
      timeZone: _DISPLAY_TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) },
  });
  container._lwChart = chart;
  const candles = chart.addCandlestickSeries({
    upColor: "#10b981", downColor: "#ef4444", borderUpColor: "#10b981", borderDownColor: "#ef4444",
    wickUpColor: "#10b981", wickDownColor: "#ef4444",
  });
  candles.setData(bars);
  const markers = tradeChartMarkers(events, bars, config.seconds);
  candles.setMarkers(markers);
  chart.timeScale().fitContent();
  if (markers.length) {
    const first = bars.findIndex(b => b.time === markers[0].time);
    const last = bars.findIndex(b => b.time === markers[markers.length - 1].time);
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(-1, first - 8), to: Math.min(bars.length, last + 8) });
  }
  if (markers.length < events.length) {
    const warning = document.createElement("div");
    warning.className = "trade-chart-fallback-msg";
    warning.textContent = `${events.length - markers.length} execution(s) have no matching historical candle. Their exact times are listed below.`;
    container.appendChild(warning);
  }
  appendTradeChartEvents(container, trade);
  const resizeObserver = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }));
  resizeObserver.observe(container);
  container._lwObserver = resizeObserver;
}

function renderTradeChartFallback(container, symbol, trade, interval) {
  const config = tradeChartConfig(interval);
  disposeTradeChart(container);
  const msg = document.createElement("div");
  msg.className = "trade-chart-fallback-msg";
  msg.textContent = "Historical candles unavailable for this trade. Entry/exit times are shown below; the live reference chart cannot display these markers.";
  container.appendChild(msg);
  appendTradeChartEvents(container, trade);
  const iframe = document.createElement("iframe");
  iframe.title = `${symbol} live reference chart (not historical trade data)`;
  iframe.src = `https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&symbol=${encodeURIComponent(symbol)}&interval=${config.tradingView}&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=rgba(0,0,0,0)&studies=&theme=${document.body.classList.contains("is-light") ? "light" : "dark"}&style=1&timezone=Europe%2FLondon&locale=en`;
  iframe.style.height = "300px";
  iframe.allow = "fullscreen";
  container.appendChild(iframe);
}

function loadTradeChart(container, symbol, trade) {
  disposeTradeChart(container);
  container._chartSymbol = symbol;
  container._chartTrade = trade;
  const interval = storedTradeChartInterval();
  const selector = $("tradeChartInterval");
  if (selector) selector.value = interval;
  const request = container._chartRequest;
  renderTradeChart(container, symbol, trade, interval, request).catch(err => {
    if (container._chartRequest !== request) return;
    console.warn("[trade-chart] fallback to iframe", err);
    renderTradeChartFallback(container, symbol, trade, interval);
  });
}

function changeTradeChartInterval(event) {
  const interval = event.target.value;
  if (!TRADE_CHART_INTERVALS[interval]) return;
  try { localStorage.setItem("journal_chart_interval", interval); } catch (_) {}
  const container = $("tradeDetailChartWrap");
  if (container?._chartSymbol && container._chartTrade) {
    loadTradeChart(container, container._chartSymbol, container._chartTrade);
  }
}

function closeTradeDetail() {
  const modal = $("tradeDetailModal");
  modal.hidden = true;
  const wrap = $("tradeDetailChartWrap");
  disposeTradeChart(wrap);
  // Only clear overflow lock if no other modal is open
  if ($("dayModal").hidden && $("weekModal").hidden && $("settingsModal").hidden) {
    document.body.style.overflow = "";
  }
}

function drawIntraday(points) {
  const canvas = $("dayModalChart");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 480;
  const h = 120;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.height = h + "px";
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  if (!points.length) return;
  const values = points.map(p => p.equity);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const range = (max - min) || 1;
  const pad = { l: 40, r: 8, t: 8, b: 14 };
  const x = (i) => pad.l + (i / Math.max(1, points.length - 1)) * (w - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - min) / range) * (h - pad.t - pad.b);

  // zero line
  ctx.strokeStyle = themeColor("chart-zero", "rgba(0,0,0,0.15)");
  if (min < 0 && max > 0) {
    const zy = y(0);
    ctx.beginPath(); ctx.moveTo(pad.l, zy); ctx.lineTo(w - pad.r, zy); ctx.stroke();
  }
  ctx.fillStyle = themeColor("chart-axis", "rgba(0,0,0,0.5)");
  ctx.font = "10px JetBrains Mono, monospace";
  ctx.textAlign = "right";
  ctx.fillText(fmt.money(max, { sign: false, compact: true }), pad.l - 4, pad.t + 8);
  ctx.fillText(fmt.money(min, { sign: false, compact: true }), pad.l - 4, h - pad.b);

  const finalV = values[values.length - 1];
  const color = finalV >= 0 ? themeColor("green", "#10b981") : themeColor("red", "#ef4444");
  const colorDim = finalV >= 0 ? themeColor("green-glow", "rgba(16,185,129,0.18)") : themeColor("red-glow", "rgba(239,68,68,0.18)");

  ctx.beginPath();
  ctx.moveTo(x(0), y(values[0]));
  values.forEach((v, i) => ctx.lineTo(x(i), y(v)));
  ctx.lineTo(x(values.length - 1), y(min));
  ctx.lineTo(x(0), y(min));
  ctx.closePath();
  ctx.fillStyle = colorDim;
  ctx.fill();

  ctx.beginPath();
  values.forEach((v, i) => { i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)); });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
}

/* ---------- equity curve ---------- */

function drawEquity(points) {
  const canvas = $("equityChart");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || canvas.parentElement.clientWidth;
  const h = 260;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.height = h + "px";
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  if (!points.length) {
    ctx.fillStyle = themeColor("chart-axis", "rgba(0,0,0,0.5)");
    ctx.font = "13px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No equity data yet.", w / 2, h / 2);
    $("equitySub").textContent = "";
    return;
  }

  const pad = { l: 60, r: 14, t: 14, b: 28 };
  const values = points.map(p => p.equity);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const range = (max - min) || 1;
  const x = (i) => pad.l + (i / Math.max(1, points.length - 1)) * (w - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - min) / range) * (h - pad.t - pad.b);

  ctx.strokeStyle = themeColor("chart-grid", "rgba(0,0,0,0.06)");
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const gy = pad.t + (i / 4) * (h - pad.t - pad.b);
    ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(w - pad.r, gy); ctx.stroke();
    const vv = max - (i / 4) * range;
    ctx.fillStyle = themeColor("chart-axis", "rgba(0,0,0,0.5)");
    ctx.font = "11px JetBrains Mono, monospace";
    ctx.textAlign = "right";
    ctx.fillText(fmt.money(vv, { sign: false }), pad.l - 6, gy + 3);
  }
  if (min < 0 && max > 0) {
    ctx.strokeStyle = themeColor("chart-zero", "rgba(0,0,0,0.22)");
    const zy = y(0);
    ctx.beginPath(); ctx.moveTo(pad.l, zy); ctx.lineTo(w - pad.r, zy); ctx.stroke();
  }

  const finalEquity = values[values.length - 1];
  const color = finalEquity >= 0 ? themeColor("green", "#10b981") : themeColor("red", "#ef4444");
  const colorDim = finalEquity >= 0 ? themeColor("green-glow", "rgba(16,185,129,0.18)") : themeColor("red-glow", "rgba(239,68,68,0.18)");
  ctx.beginPath();
  ctx.moveTo(x(0), y(values[0]));
  values.forEach((v, i) => ctx.lineTo(x(i), y(v)));
  ctx.lineTo(x(values.length - 1), y(min));
  ctx.lineTo(x(0), y(min));
  ctx.closePath();
  ctx.fillStyle = colorDim;
  ctx.fill();

  ctx.beginPath();
  values.forEach((v, i) => { i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)); });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.fillStyle = themeColor("chart-axis", "rgba(0,0,0,0.5)");
  ctx.font = "11px JetBrains Mono, monospace";
  ctx.textAlign = "center";
  [0, Math.floor(points.length / 2), points.length - 1].forEach(i => {
    if (points[i]) ctx.fillText(points[i].date, x(i), h - 8);
  });

  $("equitySub").textContent = `${points.length} trading days · ending equity ${fmt.money(finalEquity)}`;
}

/* ---------- import / clear ---------- */

async function importCsv(file) {
  if (file && file.size > 2 * 1024 * 1024) { $("statusLine").textContent = "Import files up to 2 MB at a time."; return; }
  if (!file) return;
  $("statusLine").textContent = `Importing ${file.name}…`;
  try {
    const text = await file.text();
    const data = await api("/api/journal/import-flex", {
      method: "POST",
      headers: { "Content-Type": "text/csv" },
      body: text,
    });
    if (data.error) throw new Error(data.error);
    $("statusLine").textContent = `Imported ${data.inserted} new · ${data.skipped} skipped.`;
    await refresh();
  } catch (err) {
    $("statusLine").textContent = `Import failed: ${escapeHtml(err.message)}`;
  }
}

// Never persist plaintext broker tokens in browser storage.
function getStoredCreds() {
  return _memoryCreds?.userId === (_session?.user?.id || "local")
    ? { token: _memoryCreds.token, query_id: _memoryCreds.query_id } : { token: "", query_id: "" };
}
function purgeLegacyCreds() {
  try {
    for (const key of Object.keys(localStorage)) {
      if (/^journal_ibkr_(token|query_id)(:|$)/.test(key)) localStorage.removeItem(key);
    }
  } catch (_) {}
}
async function loadConnection() {
  const userId = _session?.user?.id;
  if (!userId) return;
  try {
    const result = await api("/api/journal/connection");
    if (_session?.user?.id === userId) _connection = result;
  } catch (_) { /* secure storage may not be provisioned yet; tab-only mode */ }
}
async function saveCreds(token, queryId) {
  const userId = _session?.user?.id || "local";
  if (_connection.enabled) {
    await api("/api/journal/connection", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({token, query_id: queryId}) });
    if ((_session?.user?.id || "local") !== userId) return;
    _connection.connected = true;
    _memoryCreds = null;
  } else { _memoryCreds = {userId, token, query_id: queryId}; }
  purgeLegacyCreds();
}
async function clearCreds() {
  if (_connection.enabled) await api("/api/journal/connection", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({disconnect:true})});
  _memoryCreds = null;
  _connection.connected = false;
  purgeLegacyCreds();
}

function getStoredTheme() {
  const t = localStorage.getItem("journal_theme");
  return t === "light" ? "light" : "dark";
}

function applyTheme(theme) {
  document.body.classList.toggle("is-light", theme === "light");
}

function saveTheme(theme) {
  const t = theme === "light" ? "light" : "dark";
  localStorage.setItem("journal_theme", t);
  applyTheme(t);
}

async function syncIbkr({ silent = false } = {}) {
  const btn = $("syncBtn");
  const dot = $("syncDot");
  const creds = getStoredCreds();
  if (!_connection.connected && (!creds.token || !creds.query_id)) {
    $("statusLine").textContent = "No IBKR credentials saved — click ⚙ Settings to add yours.";
    openSettings();
    return;
  }
  btn.disabled = true;
  dot.classList.add("is-syncing");
  if (!silent) $("statusLine").textContent = "Syncing from IBKR…";
  try {
    let data;
    try {
      data = await api("/api/journal/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(_connection.connected ? {} : creds),
      });
    } catch (e) {
      data = { ok: false, error: e.message };
    }
    if (!data.ok) {
      $("statusLine").textContent = `Sync failed: ${data.error || "unknown"}`;
      dot.classList.remove("is-syncing");
      dot.classList.add("is-error");
      return;
    }
    dot.classList.remove("is-syncing", "is-error");
    dot.classList.add("is-ok");
    $("statusLine").textContent = `Synced · ${data.inserted} new · ${data.skipped} skipped (${data.format || "?"})`;
    await refresh();
    await loadLastSync();
  } catch (err) {
    $("statusLine").textContent = `Sync error: ${escapeHtml(err.message)}`;
    dot.classList.remove("is-syncing");
    dot.classList.add("is-error");
  } finally {
    btn.disabled = false;
  }
}

async function loadLastSync() {
  try {
    const data = await api("/api/journal/last-sync");
    if (data.at) {
      const when = new Date(data.at).toLocaleString();
      const r = data.result || {};
      $("lastSync").textContent = `Last sync: ${when} · +${r.inserted ?? 0} new`;
    } else {
      $("lastSync").textContent = "Last sync: never";
    }
  } catch {
    $("lastSync").textContent = "";
  }
}

async function openSettings() {
  await loadConnection();
  const creds = getStoredCreds();
  $("settingsToken").value = creds.token;
  $("settingsQueryId").value = creds.query_id;
  $("settingsTheme").value = getStoredTheme();
  $("settingsStatus").textContent = _connection.connected ? "IBKR is connected. Enter a token only to replace it." : (_connection.enabled ? "Your reporting token will be stored encrypted." : "Secure storage is not configured yet. Credentials last only for this tab.");
  $("settingsModal").hidden = false;
  document.body.style.overflow = "hidden";
}

function closeSettings() {
  $("settingsModal").hidden = true;
  $("settingsToken").value = "";
  document.body.style.overflow = "";
}

async function handleSettingsSubmit(e) {
  e.preventDefault();
  const token = $("settingsToken").value.trim();
  const queryId = $("settingsQueryId").value.trim();
  if (!token || !queryId) {
    $("settingsStatus").textContent = "Both fields are required.";
    return;
  }
  try {
    await saveCreds(token, queryId);
    saveTheme($("settingsTheme").value);
    $("settingsToken").value = "";
    $("settingsStatus").textContent = _connection.enabled ? "Saved encrypted. Click Sync IBKR." : "Ready for this tab. Click Sync IBKR. Reloading clears the token.";
  } catch (_) { $("settingsStatus").textContent = "Could not save credentials. Please try again."; }
}

async function handleSettingsClear() {
  if (!confirm("Disconnect IBKR and remove its saved reporting credentials?")) return;
  try { await clearCreds(); } catch (_) { $("settingsStatus").textContent = "Could not disconnect. Please try again."; return; }
  $("settingsToken").value = "";
  $("settingsQueryId").value = "";
  $("settingsStatus").textContent = "Credentials removed.";
}

function setAutoSync(enabled) {
  // Intentionally not persisted — auto-sync must be opted into each session
  // to avoid idle tabs racking up Supabase egress.
  if (state.autoSyncTimer) {
    clearInterval(state.autoSyncTimer);
    state.autoSyncTimer = null;
  }
  if (enabled) {
    state.autoSyncTimer = setInterval(() => syncIbkr({ silent: true }), AUTO_SYNC_MS);
    // Fire one immediately
    syncIbkr({ silent: true });
  }
}

async function clearAll() {
  if (!confirm("Delete ALL imported trades? This cannot be undone.")) return;
  try {
    const data = await api("/api/journal/clear", { method: "POST" });
    $("statusLine").textContent = `Cleared ${data.deleted} fills.`;
    await refresh();
  } catch (err) {
    $("statusLine").textContent = `Clear failed: ${escapeHtml(err.message)}`;
  }
}

/* ---------- navigation ---------- */

function changeMonth(delta) {
  let m = state.calMonth + delta;
  let y = state.calYear;
  if (m < 1) { m = 12; y--; }
  if (m > 12) { m = 1; y++; }
  state.calMonth = m;
  state.calYear = y;
  refresh();
}

document.addEventListener("DOMContentLoaded", async () => {
  // Drop legacy unscoped IBKR creds — they used to leak between users sharing
  // a browser. Per-user scoped keys (journal_ibkr_*:{uid}) are used now.
  try {
    localStorage.removeItem("journal_ibkr_token");
    localStorage.removeItem("journal_ibkr_query_id");
  } catch (_) {}
  applyPrivacy(document.body.classList.contains("is-private"));
  $("privacyToggle").addEventListener("click", togglePrivacy);
  $("tradeChartInterval")?.addEventListener("change", changeTradeChartInterval);
  window.addEventListener("storage", event => { if (event.key === "journal_hide_pnl") applyPrivacy(event.newValue === "true"); });
  window.addEventListener("pageshow", () => { try { applyPrivacy(localStorage.getItem("journal_hide_pnl") === "true"); } catch (_) {} });
  await initAuth();
  // Existing browser tokens are removed; users reconnect explicitly in Settings.
  purgeLegacyCreds();
  await Promise.all([loadConnection(), loadJournalProfile()]);
  loadGoalSettings();
  $("goalSettingsForm").addEventListener("submit", saveGoalSettings);
  $("goalMonthlyInput").addEventListener("input", previewDailyTarget);
  $("goalDaysInput").addEventListener("input", previewDailyTarget);
  $("authGateSignInBtn")?.addEventListener("click", signInWithGoogle);
  $("csvFile").addEventListener("change", (e) => importCsv(e.target.files?.[0]));
  $("refreshBtn").addEventListener("click", refresh);
  $("clearBtn").addEventListener("click", clearAll);
  $("syncBtn").addEventListener("click", () => syncIbkr());
  const fillsToggle = $("fillsToggle");
  if (fillsToggle) fillsToggle.addEventListener("click", () => {
    const panel = $("fillsPanel");
    const open = panel.classList.toggle("is-collapsed") === false;
    fillsToggle.setAttribute("aria-expanded", String(open));
  });
  [["equityToggle", "equityPanel"], ["symbolToggle", "symbolPanel"], ["dayToggle", "dayPanel"]]
    .forEach(([toggleId, panelId]) => {
      const toggle = $(toggleId);
      const panel = $(panelId);
      if (!toggle || !panel) return;
      toggle.addEventListener("click", () => {
        const open = panel.classList.toggle("is-collapsed") === false;
        toggle.setAttribute("aria-expanded", String(open));
        // Canvas draws at 0 width while its panel is display:none — redraw
        // once it's actually visible.
        if (open && panelId === "equityPanel") drawEquity(state.lastEquity);
      });
    });
  // Auto-sync is deliberately off on every page load — it triggers a fresh
  // IBKR round-trip + Supabase writes every 15 min, which is the biggest
  // driver of usage for an idle tab left open. User must opt in each session.
  $("autoSyncToggle").checked = false;
  $("autoSyncToggle").addEventListener("change", (e) => setAutoSync(e.target.checked));
  try { localStorage.removeItem("journal_auto_sync"); } catch (_) {}
  loadLastSync();
  $("calPrev").addEventListener("click", () => changeMonth(-1));
  $("calNext").addEventListener("click", () => changeMonth(1));
  $("calThisMonth").addEventListener("click", () => {
    const n = new Date();
    state.calYear = n.getFullYear();
    state.calMonth = n.getMonth() + 1;
    refresh();
  });
  // Header filter controls were removed; state.currency stays at its stored
  // default (GBP) and is used by fmt.money for display conversion only.
  document.querySelectorAll(".tab").forEach(t => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("is-active"));
      t.classList.add("is-active");
      if (t.dataset.tab === "open") {
        loadOpenPositions();
      } else {
        refresh();
      }
    });
  });
  $("dayRulesButton").addEventListener("click", toggleDayRules);
  $("dayModalClose").addEventListener("click", closeDayModal);
  $("dayModalBackdrop").addEventListener("click", closeDayModal);
  $("weekModalClose").addEventListener("click", closeWeekModal);
  $("weekModalBackdrop").addEventListener("click", closeWeekModal);
  $("tradeDetailClose").addEventListener("click", closeTradeDetail);
  $("tradeDetailBackdrop").addEventListener("click", closeTradeDetail);
  $("tradeDetailNotes").addEventListener("input", scheduleNoteSave);
  $("tradeDetailNotes").addEventListener("blur", () => {
    if (state.noteSaveTimer) { clearTimeout(state.noteSaveTimer); state.noteSaveTimer = null; saveTradeNote(); }
  });
  document.querySelectorAll(".view-toggle-btn").forEach(btn => {
    if (btn.dataset.view === state.viewMode) btn.classList.add("is-active");
    else btn.classList.remove("is-active");
    btn.setAttribute("aria-selected", btn.dataset.view === state.viewMode ? "true" : "false");
    btn.addEventListener("click", () => {
      state.viewMode = btn.dataset.view;
      localStorage.setItem("journal_view_mode", state.viewMode);
      document.querySelectorAll(".view-toggle-btn").forEach(b => {
        b.classList.toggle("is-active", b.dataset.view === state.viewMode);
        b.setAttribute("aria-selected", b.dataset.view === state.viewMode ? "true" : "false");
      });
    });
  });
  $("settingsBtn").addEventListener("click", openSettings);
  $("settingsClose").addEventListener("click", closeSettings);
  $("settingsCancel").addEventListener("click", closeSettings);
  $("settingsBackdrop").addEventListener("click", closeSettings);
  $("settingsForm").addEventListener("submit", handleSettingsSubmit);
  $("settingsClear").addEventListener("click", handleSettingsClear);
  $("settingsTheme").addEventListener("change", (e) => saveTheme(e.target.value));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("tradeDetailModal").hidden) closeTradeDetail();
    else if (!$("weekModal").hidden) closeWeekModal();
    else if (!$("dayModal").hidden) closeDayModal();
    else if (!$("settingsModal").hidden) closeSettings();
  });
  window.addEventListener("resize", () => drawEquity(state.lastEquity));
  refresh();
});
