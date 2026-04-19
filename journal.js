/* Option Riders — Trade Journal front-end */

const $ = (id) => document.getElementById(id);

const AUTO_SYNC_MS = 15 * 60 * 1000;
const BASE_CURRENCY = "USD"; // IBKR account currency for our data

let _supabase = null;
let _session = null;

async function initAuth() {
  try {
    const cfg = await fetch("/api/public-config", { cache: "no-store" }).then(r => r.json());
    const url = cfg.supabaseUrl || cfg.SUPABASE_URL || cfg.supabase_url;
    const anon = cfg.supabaseAnonKey || cfg.SUPABASE_ANON_KEY || cfg.supabase_anon_key;
    if (url && anon && window.supabase) {
      _supabase = window.supabase.createClient(url, anon);
      const { data } = await _supabase.auth.getSession();
      _session = data.session || null;
      _supabase.auth.onAuthStateChange((_e, session) => {
        _session = session;
        applyAuthGate();
      });
    }
  } catch { /* local dev — no Supabase config, stays open */ }
  applyAuthGate();
}

function applyAuthGate() {
  const gate = $("authGate");
  if (!gate) return;
  // Only gate when Supabase is configured; otherwise (local dev) pass through.
  if (_supabase && !_session) {
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
    return `<span class="sym-base">${base}</span> <span class="sym-opt">${strikeStr}</span><span class="sym-exp">${exp ? ` ${exp}` : ""}</span>`;
  }
  return `<span class="sym-base">${base}</span>`;
}

function buildQuery() {
  const qs = new URLSearchParams();
  const f = $("filterFrom").value;
  const t = $("filterTo").value;
  const a = $("filterAsset").value;
  if (f) qs.set("from", f);
  if (t) qs.set("to", t);
  if (a) qs.set("asset_class", a);
  return qs.toString();
}

async function api(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (_session?.access_token) {
    headers.set("Authorization", `Bearer ${_session.access_token}`);
  }
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

async function refresh() {
  const qs = buildQuery();
  $("statusLine").textContent = "Loading…";
  try {
    await ensureFxRate();
    const calQs = new URLSearchParams(qs);
    calQs.set("year", state.calYear);
    calQs.set("month", state.calMonth);

    const [stats, fills, equity, calendar] = await Promise.all([
      api(`/api/journal/stats?${qs}`),
      api(`/api/journal/fills?${qs}&limit=300`),
      api(`/api/journal/equity?${qs}`),
      api(`/api/journal/calendar?${calQs.toString()}`),
    ]);
    state.baseAlreadyApplied = !!stats.base_currency_applied;
    await ensureFxRate();
    state.lastEquity = equity;
    renderStats(stats);
    renderSymbolTable(stats.by_symbol);
    renderDayTable(stats.by_day);
    renderRecentTrades(fills);
    renderFills(fills);
    renderCalendar(calendar);
    drawEquity(equity);
    $("statusLine").textContent = stats.trade_count === 0
      ? "No trades yet — import a Flex CSV to begin."
      : `${stats.trade_count} fills · ${stats.close_count} closed trades · updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    $("statusLine").textContent = `Error: ${err.message}`;
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
    tbody.innerHTML = `<tr><td colspan="3" class="muted">Error: ${err.message}</td></tr>`;
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
    return `${m}-${d}-${y} ${strikeStr} ${pc}`.trim();
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
      <td>${r.symbol}</td>
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
    tr.innerHTML = `<td>${r.date}</td><td class="num ${signClass(r.pnl)}">${fmt.money(r.pnl)}</td>`;
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
      <td>${r.asset_class || ""}</td>
      <td>${r.buy_sell || ""}</td>
      <td class="num">${fmt.num(r.quantity, 0)}</td>
      <td class="num">${fmt.num(r.trade_price, 4)}</td>
      <td class="num">${fmt.money(r.proceeds, { sign: false })}</td>
      <td class="num">${fmt.money(r.commission, { sign: false })}</td>
      <td class="num ${signClass(r.realized_pnl)}">${r.realized_pnl ? fmt.money(r.realized_pnl) : "—"}</td>
      <td>${r.open_close || ""}</td>`;
    tbody.appendChild(tr);
  });
  $("fillsSub").textContent = `${rows.length} fills shown`;
  if (!rows.length) tbody.innerHTML = `<tr><td colspan="10" class="muted">No fills to show.</td></tr>`;
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
      cell.classList.add("cal-clickable");
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
    cell.innerHTML = `<div class="cal-cell-day">${d.day}</div>${pnlLine}`;
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
  const modal = $("dayModal");
  const body = document.querySelector("#dayModalTable tbody");
  body.innerHTML = `<tr><td colspan="6" class="muted">Loading…</td></tr>`;
  modal.hidden = false;
  document.body.style.overflow = "hidden";

  try {
    const d = await api(`/api/journal/day?date=${encodeURIComponent(dateIso)}`);
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
    body.innerHTML = `<tr><td colspan="6" class="muted">Error: ${err.message}</td></tr>`;
  }
}

function closeDayModal() {
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
    body.innerHTML = `<tr><td colspan="7" class="muted">Error: ${err.message}</td></tr>`;
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
      <div class="wd-label">${d.weekday} ${d.day}</div>
      <div class="wd-pnl ${d.trades ? signClass(d.pnl) : "muted"}">${d.trades ? fmt.money(d.pnl, { compact: true }) : "—"}</div>
      <div class="wd-sub">${d.trades ? `${d.trades} trade${d.trades === 1 ? "" : "s"}` : ""}</div>`;
    if (d.trades > 0) {
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

function renderWeekTrades(days, trades) {
  const tbody = document.querySelector("#weekModalTable tbody");
  tbody.innerHTML = "";
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No closed trades this week.</td></tr>`;
    return;
  }
  const weekdayByDate = new Map(days.map(d => [d.date, `${d.weekday} ${d.day}`]));
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
      <td class="week-cell-day">${dayLabel}</td>
      <td>${t.time || ""}</td>
      <td><span class="ticker-pill">${t.ticker || ""}</span></td>
      <td class="${sideClass}">${sideLabel || ""}</td>
      <td>${t.instrument || ""}</td>
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
    const timeCell = `${t.time || ""}${openTag}`;
    tr.classList.add("cal-clickable");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => openTradeDetail(t));
    tr.innerHTML = `
      <td>${timeCell}</td>
      <td><span class="ticker-pill">${t.ticker || ""}</span></td>
      <td class="${sideClass}">${sideLabel || ""}</td>
      <td>${t.instrument || ""}</td>
      <td class="num ${signClass(t.net_pnl)}">${fmt.money(t.net_pnl)}</td>
      <td class="num ${signClass(t.net_roi)}">${roi}</td>`;
    tbody.appendChild(tr);
  });
}

/* ---------- trade-detail modal ---------- */

function openTradeDetail(trade) {
  const modal = $("tradeDetailModal");
  const isOpt = trade.asset_class === "OPT" || trade.asset_class === "FOP";

  $("tradeDetailTicker").textContent = trade.ticker || "";
  $("tradeDetailInstrument").textContent = trade.instrument || trade.symbol || "";
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

  // Stat rows
  $("tdSide").textContent = sideBadge.textContent;
  $("tdEntry").textContent = fmtDisplayTime(trade.open_datetime);
  $("tdExit").textContent = trade.is_open ? "—" : fmtDisplayTime(trade.close_datetime);
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
  chartWrap.innerHTML = "";
  const underlying = (trade.ticker || trade.symbol || "").trim();
  if (underlying) {
    renderTradeChart(chartWrap, underlying, trade).catch(err => {
      console.warn("[trade-chart] fallback to iframe", err);
      renderTradeChartFallback(chartWrap, underlying);
    });
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
    status.textContent = `Error: ${err.message}`;
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
    status.textContent = `Error: ${err.message}`;
  }
}

async function renderTradeChart(container, symbol, trade) {
  container.innerHTML = `<div class="trade-chart-loading">Loading ${symbol} chart…</div>`;
  const date = (trade.open_datetime || trade.close_datetime || "").slice(0, 10);
  if (!date) throw new Error("no date on trade");

  const data = await api(`/api/journal/bars?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}`);
  if (data.error) throw new Error(data.error);
  const bars = data.bars || [];
  if (!bars.length) throw new Error("no bars returned");

  if (!window.LightweightCharts) throw new Error("lightweight-charts not loaded");

  container.innerHTML = "";
  const isLight = document.body.classList.contains("is-light");
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 340,
    layout: {
      background: { type: "solid", color: isLight ? "#ffffff" : "#0f1220" },
      textColor: isLight ? "#1f2937" : "#e8e8f0",
    },
    grid: {
      vertLines: { color: isLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.04)" },
      horzLines: { color: isLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.04)" },
    },
    rightPriceScale: { borderColor: isLight ? "rgba(0,0,0,0.1)" : "rgba(255,255,255,0.1)" },
    timeScale: {
      borderColor: isLight ? "rgba(0,0,0,0.1)" : "rgba(255,255,255,0.1)",
      timeVisible: true,
      secondsVisible: false,
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    localization: { timeFormatter: (t) => {
      const d = new Date(t * 1000);
      return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London", hourCycle: "h23" });
    }},
  });

  const candles = chart.addCandlestickSeries({
    upColor: "#10b981", downColor: "#ef4444",
    borderUpColor: "#10b981", borderDownColor: "#ef4444",
    wickUpColor: "#10b981", wickDownColor: "#ef4444",
  });
  candles.setData(bars);

  // Build entry/exit markers from the trade's fills
  const markers = [];
  (trade.fills || []).forEach(f => {
    if (!f.datetime) return;
    const qty = f.quantity || 0;
    const opening = f.open_close === "O" || (f.open_close == null && qty > 0 === (trade.put_call !== "P"));
    const isClose = f.open_close === "C";
    const ts = Math.floor(new Date(f.datetime + (f.datetime.endsWith("Z") ? "" : "-04:00")).getTime() / 1000);
    // ^ IBKR times are NY local; -04:00 during EDT. For EST (winter) it's -05:00
    //   but intraday bar timestamps are also in that same wall clock, so a
    //   consistent offset is good enough for lining up on the chart.
    markers.push({
      time: ts,
      position: qty > 0 ? "belowBar" : "aboveBar",
      color: isClose ? "#ef4444" : "#10b981",
      shape: qty > 0 ? "arrowUp" : "arrowDown",
      text: `${isClose ? "Exit" : "Entry"} ${Math.abs(qty)} @ ${f.trade_price ?? "?"}`,
    });
  });
  markers.sort((a, b) => a.time - b.time);
  candles.setMarkers(markers);

  chart.timeScale().fitContent();

  // Resize with the container
  const resizeObserver = new ResizeObserver(entries => {
    for (const entry of entries) {
      chart.applyOptions({ width: entry.contentRect.width });
    }
  });
  resizeObserver.observe(container);
  container._lwChart = chart;
  container._lwObserver = resizeObserver;
}

function renderTradeChartFallback(container, symbol) {
  container.innerHTML = "";
  const msg = document.createElement("div");
  msg.className = "trade-chart-fallback-msg";
  msg.textContent = "Intraday markers unavailable (free-tier data limit) — showing live TradingView chart.";
  container.appendChild(msg);
  const iframe = document.createElement("iframe");
  iframe.src = `https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&symbol=${encodeURIComponent(symbol)}&interval=15&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=rgba(0,0,0,0)&studies=&theme=${document.body.classList.contains("is-light") ? "light" : "dark"}&style=1&timezone=Europe%2FLondon&locale=en`;
  iframe.style.width = "100%";
  iframe.style.height = "300px";
  iframe.style.border = "0";
  iframe.allow = "fullscreen";
  container.appendChild(iframe);
}

function closeTradeDetail() {
  const modal = $("tradeDetailModal");
  modal.hidden = true;
  const wrap = $("tradeDetailChartWrap");
  if (wrap._lwObserver) { wrap._lwObserver.disconnect(); wrap._lwObserver = null; }
  if (wrap._lwChart) { wrap._lwChart.remove(); wrap._lwChart = null; }
  wrap.innerHTML = "";
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
    $("statusLine").textContent = `Import failed: ${err.message}`;
  }
}

function getStoredCreds() {
  return {
    token: localStorage.getItem("journal_ibkr_token") || "",
    query_id: localStorage.getItem("journal_ibkr_query_id") || "",
  };
}

function saveCreds(token, queryId) {
  localStorage.setItem("journal_ibkr_token", token);
  localStorage.setItem("journal_ibkr_query_id", queryId);
}

function clearCreds() {
  localStorage.removeItem("journal_ibkr_token");
  localStorage.removeItem("journal_ibkr_query_id");
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
  if (!creds.token || !creds.query_id) {
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
        body: JSON.stringify(creds),
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
    $("statusLine").textContent = `Sync error: ${err.message}`;
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

function openSettings() {
  const creds = getStoredCreds();
  $("settingsToken").value = creds.token;
  $("settingsQueryId").value = creds.query_id;
  $("settingsTheme").value = getStoredTheme();
  $("settingsStatus").textContent = "";
  $("settingsModal").hidden = false;
  document.body.style.overflow = "hidden";
}

function closeSettings() {
  $("settingsModal").hidden = true;
  document.body.style.overflow = "";
}

function handleSettingsSubmit(e) {
  e.preventDefault();
  const token = $("settingsToken").value.trim();
  const queryId = $("settingsQueryId").value.trim();
  if (!token || !queryId) {
    $("settingsStatus").textContent = "Both fields are required.";
    return;
  }
  saveCreds(token, queryId);
  saveTheme($("settingsTheme").value);
  $("settingsStatus").textContent = "Saved. Click Sync IBKR to pull your trades.";
  setTimeout(closeSettings, 600);
}

function handleSettingsClear() {
  if (!confirm("Remove saved IBKR credentials from this browser?")) return;
  clearCreds();
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
    $("statusLine").textContent = `Clear failed: ${err.message}`;
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
  await initAuth();
  $("authGateSignInBtn")?.addEventListener("click", signInWithGoogle);
  $("csvFile").addEventListener("change", (e) => importCsv(e.target.files?.[0]));
  $("refreshBtn").addEventListener("click", refresh);
  $("clearBtn").addEventListener("click", clearAll);
  $("syncBtn").addEventListener("click", () => syncIbkr());
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
  $("filterCurrency").value = state.currency;
  $("filterCurrency").addEventListener("change", (e) => {
    state.currency = e.target.value;
    localStorage.setItem("journal_currency", state.currency);
    refresh();
  });
  ["filterFrom", "filterTo", "filterAsset"].forEach(id => {
    $(id).addEventListener("change", refresh);
  });
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
