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
    const date = (r.trade_date || r.datetime || "").slice(0, 10);
    const [y, m, d] = date.split("-");
    const dateStr = y ? `${m}/${d}/${y.slice(2)}` : date;
    const timeStr = r.datetime ? r.datetime.slice(11, 19) : "";
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
    const dt = r.datetime ? r.datetime.replace("T", " ").slice(0, 16) : (r.trade_date || "");
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

  for (let i = 0; i < data.lead_blank; i++) {
    const pad = document.createElement("div");
    pad.className = "cal-cell cal-cell-blank";
    grid.appendChild(pad);
  }

  data.days.forEach(d => {
    const cell = document.createElement("div");
    cell.className = "cal-cell";
    if (d.trades > 0) {
      cell.classList.add(d.pnl > 0 ? "cal-pos" : d.pnl < 0 ? "cal-neg" : "cal-neutral");
      cell.classList.add("cal-clickable");
      cell.addEventListener("click", () => openDayModal(d.date));
    }
    const pnlLine = d.trades > 0
      ? `<div class="cal-cell-pnl ${signClass(d.pnl)}">${fmt.money(d.pnl, { compact: true })}</div>
         <div class="cal-cell-sub">${d.trades} trade${d.trades === 1 ? "" : "s"}</div>
         <div class="cal-cell-sub">${fmt.pct(d.win_rate)}</div>`
      : "";
    cell.innerHTML = `<div class="cal-cell-day">${d.day}</div>${pnlLine}`;
    grid.appendChild(cell);
  });

  // Trailing blanks to complete final row (looks cleaner)
  const total = data.lead_blank + data.days.length;
  const trailing = (7 - (total % 7)) % 7;
  for (let i = 0; i < trailing; i++) {
    const pad = document.createElement("div");
    pad.className = "cal-cell cal-cell-blank";
    grid.appendChild(pad);
  }

  // Weekly sidebar
  const weekly = $("calendarWeekly");
  weekly.innerHTML = "";
  data.weeks.forEach((w, idx) => {
    const card = document.createElement("div");
    card.className = "week-card " + (w.active_days ? signClass(w.pnl) : "empty");
    card.innerHTML = `
      <div class="week-title">Week ${idx + 1}</div>
      <div class="week-pnl">${w.active_days ? fmt.money(w.pnl, { compact: true }) : fmt.money(0, { compact: true })}</div>
      <div class="week-sub">${w.active_days} day${w.active_days === 1 ? "" : "s"}</div>`;
    weekly.appendChild(card);
  });
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
    tr.innerHTML = `
      <td>${t.time || ""}</td>
      <td><span class="ticker-pill">${t.ticker || ""}</span></td>
      <td class="${sideClass}">${sideLabel || ""}</td>
      <td>${t.instrument || ""}</td>
      <td class="num ${signClass(t.net_pnl)}">${fmt.money(t.net_pnl)}</td>
      <td class="num ${signClass(t.net_roi)}">${roi}</td>`;
    tbody.appendChild(tr);
  });
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
  localStorage.setItem("journal_auto_sync", enabled ? "1" : "0");
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
  const autoOn = localStorage.getItem("journal_auto_sync") === "1";
  $("autoSyncToggle").checked = autoOn;
  $("autoSyncToggle").addEventListener("change", (e) => setAutoSync(e.target.checked));
  if (autoOn) setAutoSync(true);
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
      // Open positions tab currently shows empty table (no open-position detection yet)
      const tbody = document.querySelector("#recentTradesTable tbody");
      if (t.dataset.tab === "open") {
        tbody.innerHTML = `<tr><td colspan="3" class="muted">Open-position detection coming soon.</td></tr>`;
      } else {
        refresh();
      }
    });
  });
  $("dayModalClose").addEventListener("click", closeDayModal);
  $("dayModalBackdrop").addEventListener("click", closeDayModal);
  $("settingsBtn").addEventListener("click", openSettings);
  $("settingsClose").addEventListener("click", closeSettings);
  $("settingsCancel").addEventListener("click", closeSettings);
  $("settingsBackdrop").addEventListener("click", closeSettings);
  $("settingsForm").addEventListener("submit", handleSettingsSubmit);
  $("settingsClear").addEventListener("click", handleSettingsClear);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("dayModal").hidden) closeDayModal();
    else if (!$("settingsModal").hidden) closeSettings();
  });
  window.addEventListener("resize", () => drawEquity(state.lastEquity));
  refresh();
});
