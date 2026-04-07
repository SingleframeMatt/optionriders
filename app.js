/* ============================================
   Option Riders — Application Logic
   ============================================ */

const DASHBOARD_DATA = {
  date: "Monday, March 16, 2026",
  lastUpdatedTime: "",
  marketStatus: "PRE-MARKET",
  sentiment: "BEARISH",
  
  catalysts: [
    "FOMC Week — Decision Wed 3/18",
    "NVIDIA GTC Keynote 11am PT", 
    "Oil Crisis: Strait of Hormuz halted",
    "Retail Sales 8:30 AM",
    "Consumer Sentiment dipped on Middle East conflict"
  ],
  
  calendar: [
    { time: "8:30 AM", event: "Retail Sales (MoM)", prior: "0.0%" },
    { time: "8:30 AM", event: "Retail Sales ex-Auto", prior: "0.0%" },
    { time: "8:30 AM", event: "Empire State Mfg Index", prior: "7.1" },
    { time: "9:15 AM", event: "Industrial Production", prior: "0.7%" },
    { time: "9:15 AM", event: "Capacity Utilization", prior: "76.2%" },
    { time: "10:00 AM", event: "NAHB Housing Index", prior: "36" },
    { time: "11:00 AM PT", event: "NVIDIA GTC Keynote", prior: "—" }
  ],
  
  indexes: [
    {
      ticker: "SPY", name: "S&P 500 ETF", price: 662.29, change: -0.57,
      rsi: 33.4, atr: 11.06, atrPct: 1.67, bias: "Bearish",
      support: [661, 656], resistance: [672, 678],
      bullTrigger: "Reclaim 668", bearTrigger: "Break below 661",
      strategy: "Oversold bounce scalp long above 668; short breakdown below 660",
      expectedMove: "±$10-11 (1.6%)"
    },
    {
      ticker: "QQQ", name: "Nasdaq 100 ETF", price: 593.72, change: -0.59,
      rsi: 39.8, atr: 11.54, atrPct: 1.94, bias: "Bearish",
      support: [591, 585], resistance: [600, 608],
      bullTrigger: "Reclaim 600", bearTrigger: "Break below 591",
      strategy: "Long on reclaim of 600 targeting 608; short below 590",
      expectedMove: "±$11-12 (1.9%)"
    },
    {
      ticker: "ES", name: "S&P 500 Futures", price: 6630, change: -0.57,
      rsi: 33, atr: 110, atrPct: 1.7, bias: "Bearish",
      support: [6610, 6560], resistance: [6720, 6780],
      bullTrigger: "Reclaim 6680", bearTrigger: "Lose 6610",
      strategy: "Bounce scalps long above 6680; short below 6600",
      expectedMove: "±110 pts (1.7%)"
    },
    {
      ticker: "NQ", name: "Nasdaq Futures", price: 21200, change: -0.59,
      rsi: 40, atr: 450, atrPct: 2.0, bias: "Bearish",
      support: [21100, 20800], resistance: [21500, 21800],
      bullTrigger: "Reclaim 21500", bearTrigger: "Lose 21100",
      strategy: "Momentum long if GTC lifts NQ above 21500; short below 21000",
      expectedMove: "±400-500 pts (2%)"
    }
  ],
  
  tickers: [],
  
  watchlist: [
    { rank: 1, ticker: "SPY", direction: "SHORT", entry: "Below 661", target: "656-652", stop: "668", catalyst: "FOMC week risk + weak breadth" },
    { rank: 2, ticker: "QQQ", direction: "SHORT", entry: "Below 591", target: "585-580", stop: "600", catalyst: "Tech weakness into Fed" },
    { rank: 3, ticker: "NVDA", direction: "LONG", entry: "Above 184", target: "190-195", stop: "178", catalyst: "GTC Keynote 11am PT" },
    { rank: 4, ticker: "MU", direction: "LONG", entry: "Above 430", target: "445-450", stop: "418", catalyst: "Momentum + #1 rated semi" },
    { rank: 5, ticker: "META", direction: "SHORT", entry: "Below 609", target: "595-600", stop: "626", catalyst: "Capitulation continuation" },
    { rank: 6, ticker: "AAPL", direction: "SHORT", entry: "Below 249", target: "242", stop: "255", catalyst: "RSI 34, deeply oversold" },
    { rank: 7, ticker: "AVGO", direction: "LONG", entry: "Above 330", target: "340-345", stop: "320", catalyst: "GTC sympathy play" }
  ],
  
  themes: [
    "NVIDIA GTC is the single most important catalyst — expect elevated volatility in NVDA, AMD, AVGO, SMCI, and QQQ/NQ after 11am PT.",
    "Oil / Middle East remains the dominant macro headwind — any Strait of Hormuz headlines will whip the entire market.",
    "Pre-FOMC positioning begins today — two-day meeting starts Tuesday, expect tighter ranges ahead of Wednesday's decision.",
    "Retail Sales data at 8:30 AM could set the early tone — watch for consumer weakness narrative.",
    "Multiple tickers at or near oversold (SPY 33, AAPL 34, META 36) — bounce candidates if any positive catalyst lands."
  ]
};

const ECONOMIC_CALENDAR = {
  sources: [
    "https://api.allorigins.win/raw?url=https%3A%2F%2Fnfs.faireconomy.media%2Fff_calendar_thisweek.json",
    "https://r.jina.ai/http://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
  ],
  events: [],
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  lastUpdated: "",
  error: "",
  country: "USD"
};

const OPTIONS_FLOW = {
  unusual: [],
  mostActive: [],
  atmSpreads: [],
  maxSpreadDollars: 0.15,
  putCallRatio: null,
  loading: true,
  error: "",
  updatedAt: ""
};

const TOP_WATCH = {
  topWatch: [],
  sourceStatus: {},
  updatedAt: "",
  loading: true,
  error: "",
};

const TOP_TRADE_TODAY = {
  picks: [],
  bestOverallPick: "",
  namesToAvoid: [],
  macroRisks: [],
  summary: "",
  sessionType: "",
  sessionLabel: "",
  marketDate: "",
  generatedAt: "",
  choppyDayWarning: false,
  loading: true,
  error: "",
};

const AUTH_STATE = {
  configLoaded: false,
  user: null,           // Supabase User object { id, email, ... }
  googleClientId: "",   // kept for legacy display only
  error: "",
  buttonRendered: false,
  // Subscription state — populated after sign-in via /api/subscription-status
  subscription: {
    checked: false,
    hasAccess: false,
    status: "none",     // mirrors Stripe status: trialing|active|past_due|canceled|none
    trialEndsAt: null,
    currentPeriodEndsAt: null,
  },
};

// Supabase JS client — initialised in initAuth() once public config is fetched.
let _supabase = null;

const APP_CONFIG = {
  tradingViewProductName: "Option Riders TradingView Script",
  tradingViewProductDescription: "Private TradingView tool with Option Riders signals and alerts directly on-chart.",
  monthlyPlan: {
    link: "",
    name: "Monthly Access",
    price: "$39/month",
    description: "Recurring access with ongoing updates.",
  },
  lifetimePlan: {
    link: "",
    name: "Lifetime Access",
    price: "$120 one-time",
    description: "One payment for lifetime access.",
  },
};

const GUEST_TICKERS_STORAGE_KEY = 'optionriders-guest-tickers-v1';
const GOOGLE_USER_STORAGE_KEY = 'optionriders-google-user-v1';
const USER_TICKERS_STORAGE_PREFIX = 'optionriders-user-tickers-v1';
const TRADE_ALERTS_STORAGE_KEY = 'optionriders-trade-alerts-v1';
const BUILT_IN_TICKERS = new Set([
  ...DASHBOARD_DATA.indexes.map((item) => item.ticker),
  ...DASHBOARD_DATA.tickers.map((item) => item.ticker),
  ...DASHBOARD_DATA.watchlist.map((item) => item.ticker),
]);
const ALERT_STATE = {
  items: [],
  activeSignals: {},
  notificationsEnabled: false,
};

// ============================================
// Utility Functions
// ============================================

function formatPrice(price) {
  if (price >= 1000) return price.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatChange(change) {
  const sign = change >= 0 ? '+' : '';
  return `${sign}${change.toFixed(2)}%`;
}

function getChangeClass(change) {
  return change >= 0 ? 'positive' : 'negative';
}

function getRsiClass(rsi) {
  if (rsi > 50) return 'rsi-green';
  if (rsi < 40) return 'rsi-red';
  return 'rsi-amber';
}

function getSignalLabel(score) {
  if (score >= 50)  return 'STRONG BUY';
  if (score >= 20)  return 'BUY';
  if (score <= -50) return 'STRONG SELL';
  if (score <= -20) return 'SELL';
  return 'NEUTRAL';
}

function getSignalClass(score) {
  if (score >= 50)  return 'signal-strong-buy';
  if (score >= 20)  return 'signal-buy';
  if (score <= -50) return 'signal-strong-sell';
  if (score <= -20) return 'signal-sell';
  return 'signal-neutral';
}

function renderSignalBadge(score) {
  if (score == null) return '';
  const label = getSignalLabel(score);
  const cls   = getSignalClass(score);
  const sign  = score > 0 ? '+' : '';
  return `<span class="signal-badge ${cls}" title="Composite signal: RSI + SMA + momentum + MACD + volume + rel-strength + ADX + Bollinger + 52W position">${sign}${score} ${label}</span>`;
}

function renderLoadingInline(title, subtitle = '') {
  return `
    <span class="section-loading-inline" role="status" aria-live="polite">
      <span class="section-loading-spinner" aria-hidden="true"></span>
      <span class="section-loading-copy">
        <span class="section-loading-title">${escapeHtml(title)}</span>
        ${subtitle ? `<span class="section-loading-subtitle">${escapeHtml(subtitle)}</span>` : ''}
      </span>
    </span>
  `;
}

function renderLoadingRow(colspan, title, subtitle = '') {
  return `
    <tr class="section-loading-row">
      <td colspan="${colspan}">
        ${renderLoadingInline(title, subtitle)}
      </td>
    </tr>
  `;
}

function getVixClass(price) {
  if (price >= 30) return 'vix-fear';
  if (price >= 20) return 'vix-elevated';
  if (price <= 14) return 'vix-calm';
  return 'vix-normal';
}

function renderVixBadge(vix) {
  if (!vix) return;
  const el = document.getElementById('vixBadge');
  if (!el) return;
  const sign = vix.changePct >= 0 ? '+' : '';
  el.className = `badge vix-badge ${getVixClass(vix.price)}`;
  el.textContent = `VIX ${vix.price} (${sign}${vix.changePct}%) ${vix.label}`;
  el.title = 'CBOE Volatility Index — >25 = elevated fear, <15 = low fear/complacency';
  el.style.display = '';
}

function renderMarketPulse(breadth) {
  if (!breadth) return;
  const el = document.getElementById('marketPulseBadge');
  if (!el) return;
  const score = breadth.avgScore;
  const sign  = score >= 0 ? '+' : '';
  const cls   = score >= 40 ? 'signal-strong-buy' :
                score >= 15 ? 'signal-buy' :
                score <= -40 ? 'signal-strong-sell' :
                score <= -15 ? 'signal-sell' : 'signal-neutral';
  el.className = `badge market-pulse-badge signal-badge ${cls}`;
  el.innerHTML = `PULSE&nbsp;${sign}${score} <span style="opacity:0.7;font-size:0.72em">${escapeHtml(breadth.label)}</span>`;
  el.title = `Market Pulse: avg signal across ${breadth.total} tickers — ${breadth.bullish} bullish, ${breadth.bearish} bearish, ${breadth.neutral} neutral`;
  el.style.display = '';
}

function renderProductOffer() {
  const section = document.getElementById('productOfferSection');
  const title = document.getElementById('productOfferTitle');
  const description = document.getElementById('productOfferDescription');
  const note = document.getElementById('productOfferNote');
  const monthlyName = document.getElementById('monthlyPlanName');
  const monthlyPrice = document.getElementById('monthlyPlanPrice');
  const monthlyDescription = document.getElementById('monthlyPlanDescription');
  const monthlyBuyBtn = document.getElementById('monthlyPlanBuyBtn');
  const lifetimeName = document.getElementById('lifetimePlanName');
  const lifetimePrice = document.getElementById('lifetimePlanPrice');
  const lifetimeDescription = document.getElementById('lifetimePlanDescription');
  const lifetimeBuyBtn = document.getElementById('lifetimePlanBuyBtn');
  if (!section || !title || !description || !note || !monthlyName || !monthlyPrice || !monthlyDescription || !monthlyBuyBtn || !lifetimeName || !lifetimePrice || !lifetimeDescription || !lifetimeBuyBtn) return;

  title.textContent = APP_CONFIG.tradingViewProductName || 'Option Riders TradingView Script';
  description.textContent = APP_CONFIG.tradingViewProductDescription || 'Private TradingView tool for traders who want the same Option Riders signal framework directly on-chart.';

  const plans = [
    { config: APP_CONFIG.monthlyPlan, nameEl: monthlyName, priceEl: monthlyPrice, descEl: monthlyDescription, buttonEl: monthlyBuyBtn },
    { config: APP_CONFIG.lifetimePlan, nameEl: lifetimeName, priceEl: lifetimePrice, descEl: lifetimeDescription, buttonEl: lifetimeBuyBtn },
  ];

  const isLiveCheckoutLink = (url) => Boolean(url) && !String(url).includes('replace-with-your');

  plans.forEach(({ config, nameEl, priceEl, descEl, buttonEl }) => {
    nameEl.textContent = config.name;
    priceEl.textContent = config.price;
    descEl.textContent = config.description;
    if (isLiveCheckoutLink(config.link)) {
      buttonEl.href = config.link;
      buttonEl.setAttribute('aria-disabled', 'false');
    } else {
      buttonEl.href = '#';
      buttonEl.setAttribute('aria-disabled', 'true');
    }
  });

  note.textContent = (APP_CONFIG.monthlyPlan.link || APP_CONFIG.lifetimePlan.link)
    ? 'Instant checkout through Stripe.'
    : 'Set your Stripe plan links to make checkout live.';
  section.style.display = '';
}

function renderEarningsDate(earningsIso) {
  if (!earningsIso) return '';
  const today   = new Date();
  today.setHours(0, 0, 0, 0);
  const eDate   = new Date(earningsIso + 'T12:00:00');
  const diffMs  = eDate - today;
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 0 || diffDays > 60) return ''; // skip past or far-future
  const shortDate = eDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const countdown = diffDays === 0 ? 'Today!' :
                    diffDays === 1 ? 'Tomorrow' :
                    `in ${diffDays}d`;
  const urgency = diffDays <= 3 ? 'earnings-urgent' : diffDays <= 10 ? 'earnings-soon' : 'earnings-normal';
  return `<span class="earnings-badge ${urgency}" title="Next earnings: ${earningsIso}">📅 Earnings ${shortDate} (${countdown})</span>`;
}

function getBiasClass(bias) {
  const lower = bias.toLowerCase();
  if (lower.includes('bullish') && !lower.includes('bearish')) return 'badge-bullish';
  if (lower.includes('bearish') && !lower.includes('bullish')) return 'badge-bearish';
  if (lower.includes('range')) return 'badge-range';
  return 'badge-neutral';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str ?? '');
  return div.innerHTML;
}

function normalizeTickerList(list) {
  const seen = new Set();
  return (Array.isArray(list) ? list : [])
    .map((item) => String(item || '').trim().toUpperCase())
    .filter((item) => item && item.length <= 5 && /^[A-Z0-9]+$/.test(item) && !seen.has(item) && seen.add(item));
}

function getTickerStorageKey(user = AUTH_STATE.user) {
  // Supabase users have `id` (UUID); legacy Google users had `sub`.
  const uid = user?.id || user?.sub;
  return uid ? `${USER_TICKERS_STORAGE_PREFIX}:${uid}` : GUEST_TICKERS_STORAGE_KEY;
}

function loadSavedTickers(user = AUTH_STATE.user) {
  try {
    const saved = window.localStorage.getItem(getTickerStorageKey(user));
    const parsed = saved ? JSON.parse(saved) : [];
    return normalizeTickerList(parsed);
  } catch (error) {
    return [];
  }
}

function saveTickerList(user = AUTH_STATE.user, list = customTickersList) {
  try {
    window.localStorage.setItem(getTickerStorageKey(user), JSON.stringify(normalizeTickerList(list)));
    return true;
  } catch (error) {
    return false;
  }
}

function loadStoredGoogleUser() {
  try {
    const saved = window.localStorage.getItem(GOOGLE_USER_STORAGE_KEY);
    const parsed = saved ? JSON.parse(saved) : null;
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (error) {
    return null;
  }
}

function saveStoredGoogleUser(user) {
  try {
    if (!user) {
      window.localStorage.removeItem(GOOGLE_USER_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(GOOGLE_USER_STORAGE_KEY, JSON.stringify(user));
  } catch (error) {
    // Ignore storage failures and keep sign-in usable for the session.
  }
}

function syncTickersForCurrentUser() {
  const uid = AUTH_STATE.user?.id || AUTH_STATE.user?.sub;
  if (!uid) {
    customTickersList = loadSavedTickers(null);
    return;
  }

  const accountTickers = loadSavedTickers(AUTH_STATE.user);
  const guestTickers = loadSavedTickers(null);
  const merged = normalizeTickerList([...accountTickers, ...guestTickers]);
  customTickersList = merged;
  saveTickerList(AUTH_STATE.user, merged);
}

function loadTradeAlerts() {
  try {
    const saved = window.localStorage.getItem(TRADE_ALERTS_STORAGE_KEY);
    const parsed = saved ? JSON.parse(saved) : null;
    ALERT_STATE.items = Array.isArray(parsed?.items) ? parsed.items.slice(0, 12) : [];
    ALERT_STATE.activeSignals = parsed && typeof parsed.activeSignals === 'object' ? parsed.activeSignals : {};
    ALERT_STATE.notificationsEnabled = parsed?.notificationsEnabled === true;
  } catch (error) {
    ALERT_STATE.items = [];
    ALERT_STATE.activeSignals = {};
    ALERT_STATE.notificationsEnabled = false;
  }
}

function saveTradeAlerts() {
  try {
    window.localStorage.setItem(TRADE_ALERTS_STORAGE_KEY, JSON.stringify({
      items: ALERT_STATE.items.slice(0, 12),
      activeSignals: ALERT_STATE.activeSignals,
      notificationsEnabled: ALERT_STATE.notificationsEnabled,
    }));
  } catch (error) {
    // ignore storage failure
  }
}

function parseTriggerLevel(text) {
  const match = String(text || '').match(/(\d+(?:\.\d+)?)/);
  return match ? Number(match[1]) : null;
}

function formatAlertTime(timestamp) {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit'
  }).format(new Date(timestamp));
}

function getTickerPrice(ticker) {
  const row = DASHBOARD_DATA.tickers.find((item) => item.ticker === ticker)
    || DASHBOARD_DATA.indexes.find((item) => item.ticker === ticker);
  return row?.price ?? null;
}

function getTickerPutCallState(ticker) {
  const row = (OPTIONS_FLOW.atmSpreads || []).find((item) => item.ticker === ticker);
  return row?.putCallRatio || null;
}

function evaluateTradeAlerts() {
  const newAlerts = [];

  for (const row of DASHBOARD_DATA.watchlist) {
    const price = getTickerPrice(row.ticker);
    const trigger = parseTriggerLevel(row.entry);
    const ratio = getTickerPutCallState(row.ticker);
    if (price == null || trigger == null) continue;

    const isLong = row.direction === 'LONG';
    const crossed = isLong ? price >= trigger : price <= trigger;
    const scoreOk = typeof row.signalScore === 'number'
      ? (isLong ? row.signalScore >= 20 : row.signalScore <= -20)
      : true;
    const optionsOk = ratio
      ? (isLong ? ratio.leader !== 'puts' : ratio.leader !== 'calls')
      : true;
    const liquidOk = (() => {
      const spreadRow = (OPTIONS_FLOW.atmSpreads || []).find((item) => item.ticker === row.ticker);
      return spreadRow ? !spreadRow.isWide : true;
    })();

    const signalKey = `${row.ticker}:${row.direction}:${row.entry}`;
    const shouldTrigger = crossed && scoreOk && optionsOk && liquidOk;
    const wasActive = Boolean(ALERT_STATE.activeSignals[signalKey]);

    if (shouldTrigger && !wasActive) {
      const alert = {
        id: `${signalKey}:${Date.now()}`,
        ticker: row.ticker,
        direction: row.direction,
        entry: row.entry,
        target: row.target,
        stop: row.stop,
        price: Number(price.toFixed(2)),
        signalScore: row.signalScore ?? null,
        putCallLabel: ratio?.label || 'n/a',
        ratioLeader: ratio?.leader || 'balanced',
        timestamp: Date.now(),
        summary: `${row.ticker} ${row.direction} triggered at ${price.toFixed(2)} vs ${row.entry}. Target ${row.target}, stop ${row.stop}.`,
      };
      ALERT_STATE.items.unshift(alert);
      ALERT_STATE.items = ALERT_STATE.items.slice(0, 12);
      newAlerts.push(alert);
    }

    ALERT_STATE.activeSignals[signalKey] = shouldTrigger;
  }

  if (newAlerts.length) {
    saveTradeAlerts();
    renderAlertCenter();
    renderAlertBar();
    notifyTradeAlerts(newAlerts);
  }
}

function notifyTradeAlerts(alerts) {
  if (!ALERT_STATE.notificationsEnabled || typeof Notification === 'undefined' || Notification.permission !== 'granted') {
    return;
  }

  alerts.forEach((alert) => {
    const body = `${alert.entry} | price ${alert.price} | target ${alert.target} | stop ${alert.stop}`;
    const notification = new Notification(`${alert.ticker} ${alert.direction} alert`, { body });
    notification.onclick = () => {
      window.focus();
      openTickerDetailModal(alert.ticker);
    };
  });
}

function renderAlertsPill() {
  const pill = document.getElementById('alertsTogglePill');
  if (!pill) return;

  const permission = typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
  let label = 'Trading Alerts Off';
  let className = 'auth-status-pill alerts-pill';

  if (permission === 'denied') {
    label = 'Trading Alerts Blocked';
    className += ' warning';
    ALERT_STATE.notificationsEnabled = false;
  } else if (permission === 'unsupported') {
    label = 'Trading Alerts Unsupported';
    className += ' warning';
    ALERT_STATE.notificationsEnabled = false;
  } else if (ALERT_STATE.notificationsEnabled && permission === 'granted') {
    label = 'Trading Alerts On';
    className += ' signed-in';
  }

  pill.textContent = label;
  pill.className = className;
  pill.disabled = permission === 'unsupported';
}

async function enableBrowserAlerts() {
  if (typeof Notification === 'undefined') {
    renderAlertsPill();
    return;
  }

  if (ALERT_STATE.notificationsEnabled) {
    ALERT_STATE.notificationsEnabled = false;
    saveTradeAlerts();
    renderAlertsPill();
    return;
  }

  const permission = Notification.permission === 'granted'
    ? 'granted'
    : await Notification.requestPermission();

  ALERT_STATE.notificationsEnabled = permission === 'granted';
  saveTradeAlerts();
  renderAlertsPill();
}

function getDisplayName(user) {
  if (!user) return '';
  // Supabase user: name lives in user_metadata (set by Google OAuth provider)
  return user.user_metadata?.full_name
    || user.user_metadata?.name
    || user.name
    || user.email
    || 'Account';
}

function decodeJwtPayload(token) {
  const payload = token.split('.')[1];
  const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
  return JSON.parse(window.atob(padded));
}

function getTimeZoneOffsetMinutes(date, timeZone) {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    timeZoneName: 'shortOffset'
  });
  const zonePart = formatter.formatToParts(date).find((part) => part.type === 'timeZoneName')?.value || 'GMT';
  const match = zonePart.match(/GMT([+-])(\d{1,2})(?::?(\d{2}))?/);

  if (!match) return 0;

  const sign = match[1] === '-' ? -1 : 1;
  const hours = Number(match[2] || 0);
  const minutes = Number(match[3] || 0);
  return sign * (hours * 60 + minutes);
}

function makeZonedDate(timeZone, year, month, day, hour, minute) {
  let utcMillis = Date.UTC(year, month - 1, day, hour, minute, 0, 0);

  // Two passes are enough for DST boundaries because the offset stabilizes immediately.
  for (let i = 0; i < 2; i += 1) {
    const offsetMinutes = getTimeZoneOffsetMinutes(new Date(utcMillis), timeZone);
    utcMillis = Date.UTC(year, month - 1, day, hour, minute, 0, 0) - (offsetMinutes * 60 * 1000);
  }

  return new Date(utcMillis);
}

function getMarketOpenTimeLabel() {
  const marketTimeZone = 'America/New_York';
  const userTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  const now = new Date();

  const marketDateParts = new Intl.DateTimeFormat('en-CA', {
    timeZone: marketTimeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(now).split('-');

  const [year, month, day] = marketDateParts.map(Number);
  const marketOpenDate = makeZonedDate(marketTimeZone, year, month, day, 9, 30);

  const localTimeLabel = new Intl.DateTimeFormat('en-US', {
    timeZone: userTimeZone,
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short'
  }).format(marketOpenDate);

  return `OPEN ${localTimeLabel}`;
}

// ============================================
// Chart Data (1-Hour OHLCV: [open, high, low, close] — 5 trading days, 7 bars/day)
// ============================================
const CHART_DATA = {
  SPY: [[666.4,667.58,662.39,664.06],[664.03,669.92,664.0,669.75],[669.77,671.6,668.38,670.87],[670.88,672.25,668.72,668.85],[668.84,670.83,668.09,670.06],[670.04,677.52,669.9,677.39],[677.37,679.91,675.89,678.31],[677.7,678.78,674.77,677.62],[677.65,681.69,677.64,681.11],[681.11,681.94,679.68,680.57],[680.63,683.36,680.61,683.27],[683.25,683.26,677.38,679.31],[679.39,680.39,677.41,677.41],[677.43,678.33,676.23,677.05],[677.59,680.08,675.2,676.15],[676.13,678.64,674.6,674.66],[674.71,675.29,673.51,674.71],[674.7,676.77,674.65,676.46],[676.46,676.62,673.34,675.25],[675.27,675.78,674.33,674.99],[674.98,676.6,674.76,676.34],[671.15,671.65,668.05,668.05],[668.06,670.55,666.92,668.21],[668.18,671.3,667.24,668.84],[668.79,670.3,667.99,668.56],[668.56,669.75,667.28,668.21],[668.2,668.48,666.88,667.98],[667.99,668.65,665.91,666.03],[669.28,672.33,667.72,668.84],[668.87,670.23,664.44,664.58],[664.57,665.31,663.1,664.33],[664.32,665.23,663.13,664.39],[664.37,664.52,662.08,663.35],[663.31,664.81,662.16,662.37],[662.36,663.0,661.37,662.3]],
  QQQ: [[594.2,596.44,591.33,593.48],[593.44,599.48,593.39,599.33],[599.33,601.35,598.07,600.45],[600.45,601.85,598.38,598.53],[598.52,600.25,597.64,599.43],[599.43,606.95,599.23,606.78],[606.74,609.25,605.36,607.76],[607.79,609.96,605.42,608.11],[608.1,612.4,608.09,611.47],[611.5,612.15,609.98,611.17],[611.23,613.28,610.87,613.17],[613.13,613.14,607.73,609.68],[609.62,610.64,607.7,607.72],[607.74,608.83,606.57,607.65],[608.95,612.43,607.58,608.75],[608.75,610.25,606.5,606.54],[606.55,607.21,605.52,606.95],[606.93,608.71,606.88,608.28],[608.29,608.5,605.05,606.83],[606.8,607.54,606.03,606.56],[606.57,608.22,606.4,607.73],[602.76,604.13,598.9,598.9],[598.91,601.37,597.54,598.99],[598.96,601.74,597.96,599.46],[599.46,601.48,599.08,599.71],[599.79,600.69,598.12,599.32],[599.34,599.57,597.71,598.81],[598.81,599.47,597.05,597.32],[599.74,603.58,598.95,600.46],[600.48,601.71,595.27,595.46],[595.46,596.13,593.58,594.57],[594.65,595.91,593.53,594.9],[595.09,595.1,592.7,594.07],[593.99,595.44,592.99,593.17],[593.31,593.83,592.59,593.62]],
  ES: [[666.4,667.58,662.39,664.06],[664.03,669.92,664.0,669.75],[669.77,671.6,668.38,670.87],[670.88,672.25,668.72,668.85],[668.84,670.83,668.09,670.06],[670.04,677.52,669.9,677.39],[677.37,679.91,675.89,678.31],[677.7,678.78,674.77,677.62],[677.65,681.69,677.64,681.11],[681.11,681.94,679.68,680.57],[680.63,683.36,680.61,683.27],[683.25,683.26,677.38,679.31],[679.39,680.39,677.41,677.41],[677.43,678.33,676.23,677.05],[677.59,680.08,675.2,676.15],[676.13,678.64,674.6,674.66],[674.71,675.29,673.51,674.71],[674.7,676.77,674.65,676.46],[676.46,676.62,673.34,675.25],[675.27,675.78,674.33,674.99],[674.98,676.6,674.76,676.34],[671.15,671.65,668.05,668.05],[668.06,670.55,666.92,668.21],[668.18,671.3,667.24,668.84],[668.79,670.3,667.99,668.56],[668.56,669.75,667.28,668.21],[668.2,668.48,666.88,667.98],[667.99,668.65,665.91,666.03],[669.28,672.33,667.72,668.84],[668.87,670.23,664.44,664.58],[664.57,665.31,663.1,664.33],[664.32,665.23,663.13,664.39],[664.37,664.52,662.08,663.35],[663.31,664.81,662.16,662.37],[662.36,663.0,661.37,662.3]],
  NQ: [[594.2,596.44,591.33,593.48],[593.44,599.48,593.39,599.33],[599.33,601.35,598.07,600.45],[600.45,601.85,598.38,598.53],[598.52,600.25,597.64,599.43],[599.43,606.95,599.23,606.78],[606.74,609.25,605.36,607.76],[607.79,609.96,605.42,608.11],[608.1,612.4,608.09,611.47],[611.5,612.15,609.98,611.17],[611.23,613.28,610.87,613.17],[613.13,613.14,607.73,609.68],[609.62,610.64,607.7,607.72],[607.74,608.83,606.57,607.65],[608.95,612.43,607.58,608.75],[608.75,610.25,606.5,606.54],[606.55,607.21,605.52,606.95],[606.93,608.71,606.88,608.28],[608.29,608.5,605.05,606.83],[606.8,607.54,606.03,606.56],[606.57,608.22,606.4,607.73],[602.76,604.13,598.9,598.9],[598.91,601.37,597.54,598.99],[598.96,601.74,597.96,599.46],[599.46,601.48,599.08,599.71],[599.79,600.69,598.12,599.32],[599.34,599.57,597.71,598.81],[598.81,599.47,597.05,597.32],[599.74,603.58,598.95,600.46],[600.48,601.71,595.27,595.46],[595.46,596.13,593.58,594.57],[594.65,595.91,593.53,594.9],[595.09,595.1,592.7,594.07],[593.99,595.44,592.99,593.17],[593.31,593.83,592.59,593.62]],
  NVDA: [[176.83,178.51,175.56,178.11],[178.09,179.48,177.99,179.18],[179.16,180.63,178.8,180.49],[180.49,180.91,179.18,179.39],[179.4,180.22,179.02,179.91],[179.9,182.07,179.29,182.03],[182.03,182.91,181.45,182.64],[182.4,184.23,182.01,184.04],[184.04,186.44,184.01,185.96],[185.96,186.12,185.05,185.3],[185.32,186.23,185.24,186.14],[186.13,186.13,184.1,184.89],[184.89,185.27,184.02,184.4],[184.4,184.83,183.26,184.76],[185.9,187.62,184.94,186.9],[186.89,186.94,185.07,185.08],[185.08,185.81,184.84,185.55],[185.55,186.07,185.25,185.61],[185.62,185.69,184.45,185.15],[185.14,185.74,185.02,185.36],[185.37,186.04,185.24,186.0],[184.03,184.86,182.05,182.09],[182.08,182.95,181.76,182.89],[182.88,184.94,182.78,184.25],[184.26,184.72,183.53,183.76],[183.77,184.19,183.17,183.54],[183.55,183.62,182.79,183.44],[183.42,183.66,182.73,183.09],[184.93,186.1,183.61,183.92],[183.91,184.25,181.67,181.89],[181.89,182.25,180.72,181.14],[181.14,181.75,180.93,181.54],[181.54,181.58,180.01,180.54],[180.53,181.13,180.28,180.71],[180.71,180.83,179.94,180.27]],
  MU: [[363.96,368.79,357.67,366.8],[366.77,378.91,366.77,377.92],[377.92,380.5,374.43,379.79],[379.88,381.5,378.31,378.88],[378.95,379.83,376.6,378.39],[378.31,388.1,377.35,387.89],[387.83,390.0,385.57,389.31],[394.01,412.0,394.01,410.42],[410.5,415.25,410.32,412.88],[412.87,414.0,409.56,411.35],[411.35,415.28,410.45,414.91],[414.87,415.17,406.28,408.65],[408.74,410.94,405.33,405.4],[405.3,405.4,401.25,403.33],[410.79,417.99,405.8,417.08],[416.99,422.72,412.85,417.87],[417.92,418.64,415.2,418.4],[418.4,421.86,418.4,420.7],[420.65,422.04,417.27,421.33],[421.31,422.65,418.76,419.57],[419.53,420.73,418.05,418.63],[410.12,413.69,402.2,402.26],[402.27,403.62,396.66,401.33],[401.39,406.55,399.68,404.53],[404.42,408.19,404.31,406.1],[406.17,408.22,404.61,407.27],[407.18,407.71,403.2,405.18],[405.23,406.77,404.17,405.41],[413.96,429.32,413.0,423.71],[423.62,425.6,416.0,422.5],[422.6,423.41,417.68,421.79],[421.61,425.89,420.06,422.55],[422.72,422.95,419.51,422.67],[422.66,426.3,422.11,423.31],[423.34,426.3,422.74,426.12]],
  META: [[634.78,637.5,626.77,630.93],[631.07,637.54,630.94,636.61],[636.52,638.23,635.36,636.75],[636.74,637.92,633.65,634.03],[634.13,635.72,633.02,634.31],[634.32,644.36,634.25,644.24],[644.13,647.74,643.0,647.35],[653.99,659.64,649.0,652.66],[652.67,660.3,652.64,657.41],[657.36,658.86,654.96,657.53],[657.9,659.88,657.27,659.12],[659.06,659.3,655.11,657.02],[657.2,657.94,652.91,653.13],[653.0,654.66,651.94,653.97],[654.76,659.15,651.35,652.82],[652.82,654.25,648.57,648.92],[649.0,651.49,648.39,651.14],[651.32,654.46,651.32,653.46],[653.57,654.46,650.56,651.95],[651.92,653.88,651.9,652.48],[652.57,655.57,652.57,654.76],[648.43,653.23,643.28,644.88],[644.8,646.64,639.4,640.58],[640.39,643.24,638.47,639.46],[639.33,641.87,638.8,639.49],[639.65,641.53,636.9,639.39],[639.34,639.62,637.8,639.07],[639.14,639.74,637.62,638.05],[623.89,627.31,617.7,626.66],[626.65,629.13,617.33,618.33],[618.3,619.64,615.18,617.79],[617.86,618.75,613.28,615.77],[615.88,615.92,609.66,613.21],[613.23,614.27,611.7,611.75],[611.82,614.83,611.78,613.59]],
  AVGO: [[327.25,338.84,323.62,337.22],[337.23,341.9,335.75,341.87],[341.82,345.82,340.54,345.06],[345.1,346.65,341.61,341.76],[341.82,345.32,340.87,343.91],[343.8,347.24,341.41,346.91],[346.83,348.49,344.41,345.78],[348.73,353.14,347.59,348.84],[348.81,351.25,346.7,346.98],[347.0,347.81,345.17,346.67],[346.76,348.39,346.04,347.66],[347.69,347.84,342.12,343.9],[343.96,344.3,340.81,342.5],[342.48,342.96,340.87,342.59],[342.31,345.8,340.75,343.3],[343.38,343.86,340.78,341.39],[341.39,342.0,339.23,340.28],[340.14,342.89,340.12,340.84],[340.84,341.09,338.25,338.85],[338.83,340.94,338.8,340.37],[340.4,342.0,339.88,341.64],[337.91,339.0,332.24,334.68],[334.62,335.95,332.2,335.53],[335.55,338.14,334.6,336.47],[336.43,339.81,336.43,337.55],[337.56,338.69,336.5,337.9],[337.86,338.03,335.2,336.69],[336.69,337.31,334.73,335.89],[337.45,338.33,331.51,333.55],[333.5,335.15,325.45,326.29],[326.29,326.36,322.92,324.18],[324.23,325.91,323.34,323.83],[324.85,325.25,321.94,324.04],[324.05,325.14,322.08,322.21],[322.91,322.91,321.46,322.1]],
  AMD: [[189.29,193.35,189.02,192.03],[191.96,196.05,191.75,195.69],[195.67,197.14,194.44,196.8],[196.77,197.91,195.96,196.45],[196.41,197.71,195.66,197.2],[197.19,202.29,197.03,202.1],[202.09,202.97,200.85,202.73],[204.43,206.59,202.2,203.16],[203.17,206.41,203.16,204.84],[204.9,204.96,203.23,204.1],[204.13,206.12,204.01,205.9],[205.89,205.95,203.19,204.06],[204.17,204.78,203.3,203.68],[203.68,203.93,202.32,203.24],[205.11,209.2,204.7,207.05],[207.0,207.11,204.99,205.34],[205.31,206.06,204.3,204.66],[204.74,205.61,204.44,205.4],[205.44,205.44,203.65,204.49],[204.4,205.09,203.72,204.2],[204.17,205.2,203.97,204.72],[202.83,203.62,198.08,198.38],[198.4,199.2,196.68,197.68],[197.64,200.0,197.3,198.77],[198.74,199.75,198.32,198.78],[198.8,199.03,197.72,198.18],[198.15,198.46,197.16,198.24],[198.26,198.6,197.08,197.8],[198.11,199.66,196.44,197.02],[197.05,197.58,194.49,194.66],[194.67,195.14,193.34,193.71],[193.72,194.46,193.24,194.03],[194.06,194.08,192.85,193.3],[193.28,193.83,192.27,192.59],[192.67,193.42,192.47,193.42]],
  AAPL: [[255.88,257.02,253.7,255.67],[255.66,257.88,255.63,257.71],[257.72,258.28,257.15,257.56],[257.59,258.09,256.54,256.63],[256.63,257.36,255.96,257.15],[257.19,259.56,256.5,259.49],[259.43,261.15,259.02,259.98],[257.65,260.25,256.97,259.96],[259.97,261.78,259.93,261.3],[261.31,261.98,261.0,261.87],[261.89,262.47,260.81,262.19],[262.19,262.48,260.47,261.65],[261.71,262.0,260.44,260.5],[260.47,261.21,260.36,260.76],[261.33,262.13,259.55,259.99],[260.0,260.97,259.85,260.11],[260.11,260.87,259.86,260.37],[255.33,256.23,254.2,255.65],[255.63,255.98,254.77,255.05],[255.06,255.67,254.81,255.39],[255.36,256.25,254.9,256.09],[256.1,256.2,254.98,255.7],[255.36,256.32,254.66,255.4],[255.44,255.81,253.27,253.31],[253.34,253.52,251.86,252.64],[252.64,252.97,250.98,251.16],[251.2,251.66,250.78,251.27],[251.25,251.85,250.22,250.3],[250.29,250.37,250.26,250.37]],
  TSLA: [[390.02,392.99,381.4,383.45],[383.45,388.59,383.45,388.33],[388.23,390.89,387.18,390.1],[390.16,390.99,388.68,389.01],[389.0,391.77,388.51,391.29],[391.27,400.7,391.05,400.6],[400.57,401.58,397.33,398.64],[402.05,406.58,400.88,401.2],[401.15,406.1,400.86,403.58],[403.55,403.81,400.95,402.65],[402.64,404.19,402.07,403.35],[403.33,403.36,398.19,400.56],[400.59,401.95,399.35,399.9],[399.86,400.74,398.27,399.23],[402.22,416.38,402.15,411.91],[411.85,412.6,408.96,409.0],[409.01,409.1,406.24,407.38],[407.4,408.65,406.25,408.23],[408.23,408.35,403.95,405.53],[405.56,406.8,404.93,406.14],[406.16,408.25,406.15,407.86],[405.22,406.5,399.44,399.53],[399.5,399.94,394.65,397.01],[396.99,400.13,396.46,398.86],[398.83,401.04,398.49,399.86],[399.85,400.45,396.27,397.84],[397.81,398.08,396.29,397.58],[397.6,398.12,394.97,395.01],[399.02,400.2,395.17,396.12],[396.14,397.73,392.22,394.08],[394.1,395.16,392.3,395.0],[394.98,395.96,392.92,394.99],[395.05,395.21,392.12,393.16],[393.12,393.96,390.08,390.9],[390.9,392.12,389.96,391.2]],
  MSFT: [[404.98,408.5,403.52,405.09],[405.0,409.16,404.67,408.56],[408.55,409.0,406.83,406.83],[406.96,407.8,405.06,405.18],[405.15,405.49,404.44,405.01],[404.97,407.91,404.4,407.9],[407.89,410.21,406.87,409.39],[410.1,410.31,402.93,404.38],[404.43,406.65,404.02,406.03],[405.99,407.37,405.2,407.24],[407.29,407.93,405.83,406.37],[406.37,406.37,404.11,405.64],[405.69,405.95,403.89,404.72],[404.7,405.94,404.25,405.71],[405.84,409.01,403.3,404.45],[404.45,405.0,401.59,402.73],[402.84,403.61,401.88,403.28],[403.25,404.5,403.0,404.23],[404.25,404.41,402.09,403.66],[403.68,404.5,403.29,403.8],[403.82,405.15,403.78,404.86],[404.41,405.77,401.83,403.5],[403.45,405.81,402.4,403.65],[403.58,405.25,402.67,404.84],[404.88,406.12,404.05,404.35],[404.35,404.85,402.64,403.06],[403.05,404.07,402.6,403.83],[403.88,403.95,401.71,401.9],[400.96,404.8,399.65,401.08],[401.11,402.54,397.52,397.78],[397.81,398.17,395.4,396.46],[396.46,396.79,394.92,396.59],[396.6,397.38,395.18,396.07],[396.08,396.58,394.5,394.57],[394.59,395.76,394.24,395.55]],
  GOOGL: [[294.36,298.65,294.1,297.11],[297.03,300.08,297.03,299.47],[299.47,301.45,298.99,300.78],[300.89,301.97,300.2,300.81],[300.79,301.93,300.68,301.07],[301.03,305.14,301.01,305.06],[305.08,306.8,304.48,306.34],[306.49,308.63,305.59,306.53],[306.55,309.5,306.54,308.42],[308.42,309.32,307.61,308.2],[308.24,309.05,307.8,308.97],[308.96,309.31,306.43,307.75],[307.74,308.37,306.62,306.63],[306.62,307.5,306.41,307.05],[306.48,310.93,305.93,310.89],[310.89,311.4,308.73,308.87],[308.89,309.82,308.37,308.76],[308.77,309.58,308.66,309.34],[309.33,309.41,307.57,308.45],[308.44,308.8,307.44,308.15],[308.18,308.98,307.82,308.7],[306.82,308.86,302.85,302.86],[302.86,303.67,301.03,302.3],[302.28,304.05,301.92,303.04],[302.98,304.31,302.85,303.81],[303.84,304.73,302.98,304.62],[304.59,305.09,303.98,304.86],[304.85,305.05,303.43,303.49],[307.08,307.82,304.42,306.68],[306.65,307.57,304.06,304.17],[304.19,304.35,302.3,302.74],[302.73,303.08,300.59,301.91],[301.97,302.05,300.45,301.96],[301.96,302.62,301.1,301.43],[301.45,302.5,300.95,302.18]],
  SMCI: [],
  PLTR: [],
  AMZN: [[210.45,212.25,207.12,209.05],[209.03,210.85,208.83,210.56],[210.55,210.75,209.83,210.13],[210.17,210.48,209.19,209.6],[209.58,209.92,208.83,209.36],[209.34,212.69,209.0,212.69],[212.69,213.82,212.42,213.45],[214.03,214.82,212.43,214.08],[214.05,215.65,214.04,214.41],[214.39,215.3,213.84,214.95],[214.97,215.65,214.79,215.36],[215.3,215.49,213.57,214.48],[214.49,214.81,213.79,213.96],[213.95,214.63,213.72,214.34],[215.88,217.0,213.06,213.62],[213.64,214.55,212.13,212.2],[212.2,212.65,211.72,212.6],[212.59,213.29,212.58,212.62],[212.64,212.79,211.33,212.32],[212.31,213.33,212.29,212.71],[212.73,213.32,212.55,212.64],[210.32,211.7,208.85,210.28],[210.26,211.17,208.15,208.63],[208.62,210.56,208.36,209.7],[209.65,210.87,209.36,210.06],[210.06,210.62,209.37,209.71],[209.69,209.89,208.81,209.79],[209.79,210.25,209.32,209.5],[209.35,210.56,207.61,209.97],[210.0,210.5,207.97,208.04],[208.04,208.4,206.86,207.79],[207.77,208.16,206.54,207.15],[207.17,207.8,206.23,207.78],[207.77,208.49,207.68,208.14],[208.13,208.5,207.37,207.72]],
};

// TradingView URL for opening full charts
function getTradingViewUrl(ticker) {
  const symbolMap = {
    'ES': 'CME_MINI:ES1!', 'NQ': 'CME_MINI:NQ1!',
    'SPY': 'AMEX:SPY', 'QQQ': 'NASDAQ:QQQ',
    'NVDA': 'NASDAQ:NVDA', 'MU': 'NASDAQ:MU',
    'META': 'NASDAQ:META', 'AVGO': 'NASDAQ:AVGO',
    'AMD': 'NASDAQ:AMD', 'AAPL': 'NASDAQ:AAPL',
    'TSLA': 'NASDAQ:TSLA', 'MSFT': 'NASDAQ:MSFT',
    'GOOGL': 'NASDAQ:GOOGL', 'AMZN': 'NASDAQ:AMZN',
    'NFLX': 'NASDAQ:NFLX', 'SMCI': 'NASDAQ:SMCI',
    'PLTR': 'NASDAQ:PLTR'
  };
  const sym = symbolMap[ticker] || ticker;
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
}

function normalizeChartBars(rawData) {
  if (!rawData) return [];
  if (rawData && Array.isArray(rawData.bars)) return normalizeChartBars(rawData.bars);
  if (!Array.isArray(rawData)) return [];

  return rawData
    .map((bar, index) => {
      if (Array.isArray(bar) && bar.length >= 4) {
        return { t: null, o: Number(bar[0]), h: Number(bar[1]), l: Number(bar[2]), c: Number(bar[3]), i: index };
      }
      if (bar && typeof bar === 'object') {
        return {
          t: bar.t || bar.time || null,
          o: Number(bar.o ?? bar.open),
          h: Number(bar.h ?? bar.high),
          l: Number(bar.l ?? bar.low),
          c: Number(bar.c ?? bar.close),
          v: Number(bar.v ?? bar.volume),
          i: index,
        };
      }
      return null;
    })
    .filter((bar) => bar && [bar.o, bar.h, bar.l, bar.c].every((value) => Number.isFinite(value)));
}

function formatChartXAxisLabel(date, previousDate = null) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
  const changedDay = !previousDate || date.toDateString() !== previousDate.toDateString();
  return changedDay
    ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : date.toLocaleTimeString('en-US', { hour: 'numeric' }).toUpperCase();
}

function formatChartChangePercent(changeValue) {
  if (!Number.isFinite(changeValue)) return '';
  const sign = changeValue >= 0 ? '+' : '';
  return `${sign}${changeValue.toFixed(2)}%`;
}

function getChartPresentationMeta(rawChartData) {
  const bars = normalizeChartBars(rawChartData);
  const timeframe = rawChartData && typeof rawChartData === 'object' && !Array.isArray(rawChartData)
    ? String(rawChartData.timeframe || '').toUpperCase()
    : '';
  const datedBars = bars
    .map((bar) => (bar.t ? new Date(bar.t) : null))
    .filter((date) => date instanceof Date && !Number.isNaN(date.getTime()));

  const lastDate = datedBars.length ? datedBars[datedBars.length - 1] : null;
  const sessionLabel = lastDate
    ? lastDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : 'Live';

  return {
    timeframe: timeframe || '1H',
    sessionLabel,
  };
}

// Draw a candlestick chart with support/resistance levels, price labels, time/day labels, and modal header styling
function drawCandlestickChart(canvas, rawChartData, levels, options = {}) {
  const bars = normalizeChartBars(rawChartData);
  if (!canvas || bars.length < 2) return;
  const chartMeta = getChartPresentationMeta(rawChartData);

  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const showRichHeader = Boolean(options.showRichHeader);
  const pad = showRichHeader
    ? { top: 34, right: 64, bottom: 22, left: 18 }
    : { top: 20, right: 66, bottom: 24, left: 14 };
  const chartW = Math.max(10, w - pad.left - pad.right);
  const volumeRegionH = showRichHeader ? Math.max(16, h * 0.11) : 0;
  const chartH = Math.max(10, h - pad.top - pad.bottom - volumeRegionH);
  const volumeTop = pad.top + chartH;

  const candlePrices = bars.flatMap((bar) => [bar.h, bar.l]);
  const candleMin = Math.min(...candlePrices);
  const candleMax = Math.max(...candlePrices);
  const candleRange = candleMax - candleMin || 1;

  let filteredLevels = null;
  if (levels) {
    const margin = candleRange * 0.5;
    const validSupport = (levels.support || []).filter((s) => s >= candleMin - margin && s <= candleMax + margin);
    const validResistance = (levels.resistance || []).filter((r) => r >= candleMin - margin && r <= candleMax + margin);
    if (validSupport.length || validResistance.length) {
      filteredLevels = { support: validSupport, resistance: validResistance };
    }
  }

  const latestClose = bars[bars.length - 1].c;
  const allPrices = [...candlePrices, latestClose];
  if (filteredLevels) {
    filteredLevels.support.forEach((s) => allPrices.push(s));
    filteredLevels.resistance.forEach((r) => allPrices.push(r));
  }
  const dataMin = Math.min(...allPrices);
  const dataMax = Math.max(...allPrices);
  const paddedRange = (dataMax - dataMin) || 1;
  const pMin = dataMin - paddedRange * 0.08;
  const pMax = dataMax + paddedRange * 0.08;
  const pRange = pMax - pMin;

  function priceToY(price) {
    return pad.top + chartH - ((price - pMin) / pRange) * chartH;
  }

  const slotW = chartW / bars.length;
  const candleW = Math.max(3, slotW * 0.58);

  ctx.clearRect(0, 0, w, h);

  ctx.save();
  const bgGradient = ctx.createLinearGradient(0, 0, 0, h);
  bgGradient.addColorStop(0, 'rgba(41, 46, 58, 0.98)');
  bgGradient.addColorStop(1, 'rgba(35, 40, 52, 0.98)');
  ctx.fillStyle = bgGradient;
  ctx.fillRect(0, 0, w, h);
  ctx.restore();

  if (showRichHeader) {
    const lastBar = bars[bars.length - 1];
    const prevClose = bars[bars.length - 2]?.c ?? lastBar.o;
    const absMove = lastBar.c - prevClose;
    const pctMove = prevClose ? (absMove / prevClose) * 100 : 0;
    const changeColor = absMove >= 0 ? '#22d36e' : '#ff6666';
    const lastDate = lastBar.t ? new Date(lastBar.t) : null;
    const headerDate = lastDate instanceof Date && !Number.isNaN(lastDate.getTime())
      ? lastDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : '';

    ctx.save();
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(206, 214, 236, 0.94)';
    ctx.font = '700 11px Space Grotesk, system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(options.symbol || '', 14, 16);
    ctx.fillStyle = 'rgba(176, 184, 207, 0.86)';
    ctx.font = '600 5px Space Grotesk, system-ui, sans-serif';
    ctx.fillText(headerDate, 50, 16);
    ctx.fillStyle = changeColor;
    ctx.font = '700 6px Space Grotesk, system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(`${formatPrice(absMove)} (${formatChartChangePercent(pctMove)})`, w - 72, 16);
    ctx.fillStyle = 'rgba(115, 206, 255, 0.88)';
    ctx.font = '600 5px Space Grotesk, system-ui, sans-serif';
    ctx.fillText('finviz.com', w - 10, 16);
    ctx.restore();
  }

  ctx.save();
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + chartW, y);
    ctx.stroke();
  }
  ctx.restore();

  const datedBars = bars
    .map((bar, index) => ({ ...bar, idx: index, date: bar.t ? new Date(bar.t) : null }))
    .filter((bar) => bar.date instanceof Date && !Number.isNaN(bar.date.getTime()));

  if (datedBars.length) {
    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.09)';
    ctx.setLineDash([4, 6]);
    let previousDayKey = '';
    datedBars.forEach((bar) => {
      const dayKey = bar.date.toDateString();
      if (dayKey === previousDayKey) return;
      previousDayKey = dayKey;
      const x = pad.left + slotW * bar.idx + slotW / 2;
      ctx.beginPath();
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, pad.top + chartH);
      ctx.stroke();
    });
    ctx.restore();
  }

  if (showRichHeader) {
    ctx.save();
    ctx.translate(12, pad.top + chartH * 0.42);
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = 'rgba(181, 188, 209, 0.84)';
    ctx.font = '700 6px Space Grotesk, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(chartMeta.timeframe, 0, 0);
    ctx.restore();
  }

  if (filteredLevels) {
    ctx.save();
    ctx.setLineDash([7, 5]);
    ctx.lineWidth = 1;
    ctx.font = showRichHeader ? '5px JetBrains Mono, monospace' : '9px JetBrains Mono, monospace';
    ctx.textBaseline = 'middle';

    (filteredLevels.support || []).forEach((level) => {
      const y = priceToY(level);
      ctx.strokeStyle = 'rgba(0,255,136,0.30)';
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + chartW, y);
      ctx.stroke();
      ctx.fillStyle = 'rgba(0,255,136,0.52)';
      ctx.textAlign = 'right';
      ctx.fillText(formatPrice(level), pad.left + chartW - 8, y);
    });

    (filteredLevels.resistance || []).forEach((level) => {
      const y = priceToY(level);
      ctx.strokeStyle = 'rgba(255,82,82,0.30)';
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + chartW, y);
      ctx.stroke();
      ctx.fillStyle = 'rgba(255,82,82,0.52)';
      ctx.textAlign = 'right';
      ctx.fillText(formatPrice(level), pad.left + chartW - 8, y);
    });
    ctx.restore();
  }

  const latestY = priceToY(latestClose);
  ctx.save();
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = bars[bars.length - 1].c >= bars[bars.length - 1].o ? 'rgba(0,255,136,0.32)' : 'rgba(255,82,82,0.32)';
  ctx.beginPath();
  ctx.moveTo(pad.left, latestY);
  ctx.lineTo(pad.left + chartW, latestY);
  ctx.stroke();
  ctx.restore();

  bars.forEach((bar, index) => {
    const x = pad.left + slotW * index + slotW / 2;
    const bullish = bar.c >= bar.o;
    const bodyColor = bullish ? '#00ff88' : '#ff5252';
    const wickColor = bullish ? 'rgba(0,255,136,0.66)' : 'rgba(255,82,82,0.66)';
    const yHigh = priceToY(bar.h);
    const yLow = priceToY(bar.l);
    const yOpen = priceToY(bar.o);
    const yClose = priceToY(bar.c);

    ctx.strokeStyle = wickColor;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(x, yHigh);
    ctx.lineTo(x, yLow);
    ctx.stroke();

    const bodyTop = Math.min(yOpen, yClose);
    const bodyHeight = Math.max(Math.abs(yOpen - yClose), 1.5);
    ctx.fillStyle = bodyColor;
    ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyHeight);
  });

  const volumeValues = bars.map((bar) => Number.isFinite(bar.v) ? bar.v : 0);
  const maxVolume = Math.max(...volumeValues, 0);
  if (showRichHeader && maxVolume > 0) {
    bars.forEach((bar, index) => {
      if (!Number.isFinite(bar.v) || bar.v <= 0) return;
      const x = pad.left + slotW * index + slotW / 2;
      const barH = Math.max(1, (bar.v / maxVolume) * (volumeRegionH - 2));
      const bullish = bar.c >= bar.o;
      ctx.fillStyle = bullish ? 'rgba(34, 211, 110, 0.35)' : 'rgba(255, 102, 102, 0.35)';
      ctx.fillRect(x - Math.max(1.5, candleW / 2), volumeTop + volumeRegionH - barH, Math.max(3, candleW), barH);
    });

    ctx.save();
    ctx.fillStyle = 'rgba(181, 188, 209, 0.72)';
    ctx.font = '7px Space Grotesk, system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const maxVolumeM = maxVolume / 1000000;
    const halfVolumeM = maxVolumeM / 2;
    ctx.fillText(`${Math.round(maxVolumeM)}M`, 2, volumeTop + 6);
    ctx.fillText(`${Math.round(halfVolumeM)}M`, 2, volumeTop + volumeRegionH * 0.5);
    ctx.restore();
  }

  ctx.save();
  ctx.font = showRichHeader ? '5px Space Grotesk, system-ui, sans-serif' : '9px JetBrains Mono, monospace';
  ctx.fillStyle = showRichHeader ? 'rgba(184, 192, 214, 0.86)' : 'rgba(255,255,255,0.38)';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i += 1) {
    const price = pMax - (pRange / 4) * i;
    const y = pad.top + (chartH / 4) * i;
    ctx.fillText(formatPrice(price), w - 10, y);
  }
  ctx.restore();

  if (datedBars.length) {
    const desiredTicks = Math.min(showRichHeader ? 4 : 4, datedBars.length);
    const step = Math.max(1, Math.floor(datedBars.length / desiredTicks));
    ctx.save();
    ctx.font = showRichHeader ? '5px Space Grotesk, system-ui, sans-serif' : '7px JetBrains Mono, monospace';
    ctx.fillStyle = showRichHeader ? 'rgba(184, 192, 214, 0.78)' : 'rgba(255,255,255,0.34)';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    let previousDate = null;

    for (let i = 0; i < datedBars.length; i += step) {
      const bar = datedBars[i];
      const x = pad.left + slotW * bar.idx + slotW / 2;
      ctx.fillText(formatChartXAxisLabel(bar.date, previousDate), x, h - pad.bottom + 4);
      previousDate = bar.date;
    }

    const lastBar = datedBars[datedBars.length - 1];
    const lastX = pad.left + slotW * lastBar.idx + slotW / 2;
    ctx.fillText(formatChartXAxisLabel(lastBar.date, previousDate), lastX, h - pad.bottom + 4);
    ctx.restore();
  }

  ctx.save();
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + chartH);
  ctx.lineTo(pad.left + chartW, pad.top + chartH);
  ctx.stroke();
  ctx.restore();

  const markerText = formatPrice(latestClose);
  ctx.save();
  ctx.font = showRichHeader ? '700 6px Space Grotesk, system-ui, sans-serif' : 'bold 11px JetBrains Mono, monospace';
  const tagPaddingX = 8;
  const tagHeight = showRichHeader ? 14 : 22;
  const textWidth = ctx.measureText(markerText).width;
  const tagWidth = textWidth + tagPaddingX * 2;
  const tagX = w - tagWidth - 6;
  const tagY = Math.max(pad.top + 2, Math.min(latestY - tagHeight / 2, pad.top + chartH - tagHeight - 2));
  ctx.fillStyle = 'rgba(255, 196, 61, 0.96)';
  ctx.fillRect(tagX, tagY, tagWidth, tagHeight);
  ctx.fillStyle = '#111318';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(markerText, tagX + tagPaddingX, tagY + tagHeight / 2);
  ctx.restore();
}

// Get levels for a ticker from DASHBOARD_DATA
function getLevelsForTicker(ticker) {
  // Check indexes
  const idx = DASHBOARD_DATA.indexes.find(i => i.ticker === ticker);
  if (idx) return { support: idx.support, resistance: idx.resistance };
  // Check ranked tickers
  const t = DASHBOARD_DATA.tickers.find(t => t.ticker === ticker);
  if (t) return { support: t.support, resistance: t.resistance };
  return null;
}

// Initialize all candlestick charts after render
function initAllCharts() {
  document.querySelectorAll('.sparkline-canvas').forEach(canvas => {
    const ticker = canvas.dataset.ticker;
    const data = CHART_DATA[ticker];
    const levels = getLevelsForTicker(ticker);
    if (data) drawCandlestickChart(canvas, data, levels);
  });
}

// Redraw charts on window resize
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(initAllCharts, 200);
});

// ============================================
// Render Functions
// ============================================

function renderHeader() {
  const sessionDate    = document.getElementById('sessionDate');
  const sessionUpdated = document.getElementById('sessionUpdated');
  if (sessionDate) {
    const now = new Date();
    sessionDate.textContent = now.toLocaleDateString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
    }).toUpperCase();
  }
  if (sessionUpdated) {
    sessionUpdated.textContent = DASHBOARD_DATA.lastUpdatedTime
      ? `Updated ${DASHBOARD_DATA.lastUpdatedTime}`
      : '';
  }
  document.getElementById('marketStatus').textContent = DASHBOARD_DATA.marketStatus;
  document.getElementById('marketOpenTime').textContent = getMarketOpenTimeLabel();
  
  const sentimentEl = document.getElementById('sentiment');
  sentimentEl.textContent = DASHBOARD_DATA.sentiment;
  sentimentEl.classList.add(
    DASHBOARD_DATA.sentiment === 'BEARISH' ? 'badge-sentiment-bearish' : 'badge-sentiment-bullish'
  );
}

function renderAuthControls() {
  const controls = document.getElementById('authControls');
  if (!controls) return;

  if (!AUTH_STATE.configLoaded) {
    controls.innerHTML = `<span class="auth-status-pill">Auth loading...</span>`;
    return;
  }

  if (AUTH_STATE.error) {
    controls.innerHTML = `
      <span class="auth-status-pill error">${escapeHtml(AUTH_STATE.error)}</span>
      <button class="auth-action-btn" type="button" onclick="initAuth(true)">Retry</button>
    `;
    return;
  }

  if (!AUTH_STATE.user) {
    controls.innerHTML = `<span class="auth-status-pill warning">Sign in required</span>`;
    renderAuthGate();
    return;
  }

  const sub = AUTH_STATE.subscription;
  const subLabel = sub.checked
    ? (sub.hasAccess
        ? (sub.status === 'trialing' ? ' · Trial' : ' · Active')
        : ' · No access')
    : ' · Checking…';

  const now = new Date();
  const dateLabel = now.toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
  }).toUpperCase();
  const timeLabel = now.toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short'
  });
  controls.innerHTML = `
    <span class="auth-status-pill signed-in">
      <span class="signed-in-name">${escapeHtml(getDisplayName(AUTH_STATE.user))}${escapeHtml(subLabel)}</span>
      <span class="signed-in-ts">${escapeHtml(dateLabel)} · ${escapeHtml(timeLabel)}</span>
    </span>
    <button class="auth-action-btn" type="button" onclick="signOut()">Sign out</button>
  `;
  renderAuthGate();
}

function renderCatalysts() {
  const strip = document.getElementById('catalystStrip');
  strip.innerHTML = DASHBOARD_DATA.catalysts.map(c => 
    `<span class="catalyst-pill">${escapeHtml(c)}</span>`
  ).join('');
}

const MARKET_RADAR_LAYOUT = [
  { x: 50, y: 50, size: 1.22 },
  { x: 28, y: 28, size: 0.94 },
  { x: 71, y: 29, size: 0.96 },
  { x: 26, y: 67, size: 0.9 },
  { x: 73, y: 68, size: 0.9 },
  { x: 49, y: 18, size: 0.8 },
  { x: 16, y: 49, size: 0.76 },
  { x: 84, y: 50, size: 0.76 },
  { x: 42, y: 82, size: 0.72 },
  { x: 59, y: 84, size: 0.72 },
  { x: 13, y: 20, size: 0.68 },
  { x: 87, y: 19, size: 0.68 },
];
const MIN_MARKET_RADAR_BUBBLES = 8;
const MARKET_RADAR_CURATED_PRIORITY = [
  { ticker: 'SMCI', direction: 'SHORT', catalyst: 'Bearish momentum + technical breakdown' },
  { ticker: 'AMD', direction: 'LONG', catalyst: 'AI sympathy and semi momentum' },
  { ticker: 'MU', direction: 'SHORT', catalyst: 'Largest expected move on the board' },
  { ticker: 'TSLA', direction: 'SHORT', catalyst: 'High-beta tape leader with outsized intraday range' },
  { ticker: 'NVDA', direction: 'LONG', catalyst: 'Semiconductor leader and key AI read-through' },
  { ticker: 'AVGO', direction: 'SHORT', catalyst: 'Heavy semi participation with elevated expected move' },
  { ticker: 'PLTR', direction: 'SHORT', catalyst: 'Momentum name with active options interest' },
  { ticker: 'AMZN', direction: 'LONG', catalyst: 'Mega-cap leadership and cross-source traction' },
];
const MARKET_RADAR_EDITORIAL_FALLBACKS = [
  {
    ticker: 'AMD',
    direction: 'LONG',
    bias: 'Bullish',
    catalyst: 'AI sympathy and semi momentum',
    expectedMovePct: 1.9,
  },
  {
    ticker: 'TSLA',
    direction: 'LONG',
    bias: 'High Beta',
    catalyst: 'High-beta headline magnet with outsized intraday ranges',
    expectedMovePct: 2.1,
  },
];

function parseExpectedMovePercent(item = {}) {
  if (typeof item.expectedMovePct === 'number') return item.expectedMovePct;
  const expectedMove = String(item.expectedMove || '');
  const pctMatch = expectedMove.match(/\(([-+]?\d+(?:\.\d+)?)%\)/);
  if (pctMatch) return Number(pctMatch[1]);
  if (typeof item.atrPct === 'number') return item.atrPct;
  return 0;
}

function getRadarTone(item) {
  const direction = String(item.direction || '').toUpperCase();
  const bias = String(item.bias || '').toLowerCase();
  if (direction === 'LONG' || (bias.includes('bullish') && !bias.includes('bearish'))) return 'long';
  if (direction === 'SHORT' || (bias.includes('bearish') && !bias.includes('bullish'))) return 'short';
  return 'neutral';
}

function getMarketRadarLookup() {
  const lookup = new Map();
  const register = (item, extra = {}) => {
    if (!item?.ticker) return;
    const existing = lookup.get(item.ticker) || {};
    lookup.set(item.ticker, { ...existing, ...item, ...extra });
  };

  (DASHBOARD_DATA.tickers || []).forEach((item) => register(item, {
    changePct: typeof item.change === 'number' ? item.change : (typeof item.friChange === 'number' ? item.friChange : null),
  }));
  (DASHBOARD_DATA.watchlist || []).forEach((item) => register(item));
  (TOP_WATCH.topWatch || []).forEach((item) => register(item));

  return lookup;
}

function buildMarketRadarItems() {
  const merged = new Map();
  const watchlistItems = Array.isArray(DASHBOARD_DATA.watchlist) ? DASHBOARD_DATA.watchlist : [];
  const topWatchItems = Array.isArray(TOP_WATCH.topWatch) ? TOP_WATCH.topWatch : [];
  const rankedTickers = Array.isArray(DASHBOARD_DATA.tickers) ? DASHBOARD_DATA.tickers : [];
  const lookup = getMarketRadarLookup();

  MARKET_RADAR_CURATED_PRIORITY.forEach((priority, index) => {
    const item = lookup.get(priority.ticker);
    if (!item) return;
    const expectedMovePct = parseExpectedMovePercent(item);
    merged.set(priority.ticker, {
      ...item,
      ticker: priority.ticker,
      direction: priority.direction || item.direction || '',
      catalyst: priority.catalyst || item.catalyst || item.strategy || item.bias || 'Curated watch',
      expectedMove: item.expectedMove || '',
      expectedMovePct,
      sourceCount: Math.max(item.sourceCount || 0, 1),
      score:
        400
        - index * 18
        + expectedMovePct * 28
        + Math.max(0, Math.abs(Number(item.signalScore) || 0) * 0.25)
        + Math.max(0, Math.abs(Number(item.relStrength) || 0) * 2),
    });
  });

  watchlistItems.forEach((item, index) => {
    if (merged.has(item.ticker)) return;
    const details = getTickerDetails(item.ticker) || {};
    const expectedMovePct = parseExpectedMovePercent(details);
    merged.set(item.ticker, {
      ticker: item.ticker,
      rank: item.rank || index + 1,
      direction: item.direction || '',
      catalyst: item.catalyst || '',
      signalScore: typeof item.signalScore === 'number' ? item.signalScore : details.signalScore,
      relStrength: typeof item.relStrength === 'number' ? item.relStrength : details.relStrength,
      price: typeof details.price === 'number' ? details.price : null,
      changePct: typeof details.change === 'number' ? details.change : null,
      expectedMove: details.expectedMove || '',
      expectedMovePct,
      sourceCount: 1,
      score:
        expectedMovePct * 18 +
        Math.max(0, 48 - index * 4)
        + Math.max(0, Math.abs(Number(item.signalScore) || 0) * 0.38)
        + (item.direction === 'LONG' || item.direction === 'SHORT' ? 10 : 0)
        + Math.max(0, Math.abs(Number(item.relStrength) || 0) * 2.5),
    });
  });

  topWatchItems.forEach((item, index) => {
    if (merged.has(item.ticker)) return;
    const existing = merged.get(item.ticker) || {};
    const details = getTickerDetails(item.ticker) || {};
    const scoreBase = Math.max(0, 16 - index);
    const expectedMovePct = parseExpectedMovePercent(details);
    merged.set(item.ticker, {
      ticker: item.ticker,
      rank: existing.rank || index + 1,
      direction: existing.direction || '',
      catalyst: existing.catalyst || `Seen on ${item.sourceCount || 0} sources`,
      signalScore: typeof existing.signalScore === 'number' ? existing.signalScore : details.signalScore,
      relStrength: typeof existing.relStrength === 'number' ? existing.relStrength : details.relStrength,
      price: typeof item.price === 'number' ? item.price : details.price ?? null,
      changePct: typeof item.changePct === 'number' ? item.changePct : details.change ?? null,
      expectedMove: details.expectedMove || existing.expectedMove || '',
      expectedMovePct,
      sourceCount: Math.max(existing.sourceCount || 0, item.sourceCount || 0),
      score:
        (existing.score || 0)
        + expectedMovePct * 16
        + scoreBase
        + (item.sourceCount || 0) * 11
        + Math.max(0, Math.abs(Number(existing.signalScore ?? details.signalScore) || 0) * 0.2),
      bias: details.bias || existing.bias || '',
    });
  });

  rankedTickers
    .slice()
    .sort((a, b) => parseExpectedMovePercent(b) - parseExpectedMovePercent(a))
    .forEach((item, index) => {
      if (merged.has(item.ticker)) return;
      const expectedMovePct = parseExpectedMovePercent(item);
      merged.set(item.ticker, {
        ticker: item.ticker,
        rank: item.rank || index + 1,
        direction: '',
        catalyst: item.strategy || item.bias || 'Expected move leader',
        signalScore: item.signalScore,
        relStrength: item.relStrength,
        price: typeof item.price === 'number' ? item.price : null,
        changePct: typeof item.change === 'number' ? item.change : (typeof item.friChange === 'number' ? item.friChange : null),
        expectedMove: item.expectedMove || '',
        expectedMovePct,
        sourceCount: 1,
        bias: item.bias || '',
        score:
          expectedMovePct * 24
          + Math.max(0, 26 - index * 2.5)
          + Math.max(0, Math.abs(Number(item.signalScore) || 0) * 0.28)
          + Math.max(0, Math.abs(Number(item.relStrength) || 0) * 2.5),
      });
    });

  MARKET_RADAR_EDITORIAL_FALLBACKS.forEach((item, index) => {
    if (merged.has(item.ticker)) return;
    const expectedMovePct = parseExpectedMovePercent(item);
    merged.set(item.ticker, {
      ticker: item.ticker,
      rank: item.rank || index + 1,
      direction: item.direction || '',
      catalyst: item.catalyst || 'Editorial watch',
      signalScore: item.signalScore,
      relStrength: item.relStrength,
      price: typeof item.price === 'number' ? item.price : null,
      changePct: typeof item.changePct === 'number' ? item.changePct : null,
      expectedMove: item.expectedMove || '',
      expectedMovePct,
      sourceCount: 1,
      bias: item.bias || '',
      score:
        expectedMovePct * 22
        + Math.max(0, 18 - index * 2),
    });
  });

  return Array.from(merged.values())
    .map((item) => ({
      ...item,
      tone: getRadarTone(item),
    }))
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, Math.max(MIN_MARKET_RADAR_BUBBLES, Math.min(MARKET_RADAR_LAYOUT.length, merged.size)));
}

function renderMarketRadarStats(items) {
  const stats = document.getElementById('marketRadarStats');
  if (!stats) return;
  if (!items.length) {
    stats.innerHTML = '';
    return;
  }

  const lead = items[0];
  const longCount = items.filter((item) => item.tone === 'long').length;
  const shortCount = items.filter((item) => item.tone === 'short').length;
  const strongest = items.reduce((best, item) => (Math.abs(item.signalScore || 0) > Math.abs(best.signalScore || 0) ? item : best), items[0]);
  const moveLeader = items.reduce((best, item) => ((item.expectedMovePct || 0) > (best.expectedMovePct || 0) ? item : best), items[0]);
  const focusLabel = lead.catalyst || 'Cross-source momentum';
  const biasLabel = longCount === shortCount ? 'Balanced board' : longCount > shortCount ? `${longCount} long setups leading` : `${shortCount} short setups leading`;
  const conviction = moveLeader.expectedMovePct ? `${moveLeader.ticker} ${moveLeader.expectedMovePct.toFixed(1)}% move` : (strongest.signalScore != null ? `${strongest.ticker} ${strongest.signalScore > 0 ? '+' : ''}${strongest.signalScore}` : `${lead.ticker} in focus`);

  stats.innerHTML = `
    <div class="market-radar-stat">
      <div class="market-radar-stat-label">Lead Setup</div>
      <div class="market-radar-stat-value">${escapeHtml(lead.ticker)} · ${escapeHtml(focusLabel)}</div>
    </div>
    <div class="market-radar-stat">
      <div class="market-radar-stat-label">Board Bias</div>
      <div class="market-radar-stat-value">${escapeHtml(biasLabel)}</div>
    </div>
    <div class="market-radar-stat">
      <div class="market-radar-stat-label">Highest Conviction</div>
      <div class="market-radar-stat-value">${escapeHtml(conviction)}</div>
    </div>
  `;
}

function getMarketRadarBubbleSizes(items, grid) {
  if (!items.length) return [];

  const gridWidth = Math.max(grid?.clientWidth || 0, 320);
  const gridHeight = Math.max(grid?.clientHeight || 0, 320);
  const edgeGap = 4;
  const bubbleGap = 0;

  const proposedSizes = items.map((item, index) => {
    const slot = MARKET_RADAR_LAYOUT[index] || MARKET_RADAR_LAYOUT[MARKET_RADAR_LAYOUT.length - 1];
    const base = Math.max(84, Math.min(178, 84 + (item.score || 0) * 0.9));
    return Math.round(base * slot.size);
  });

  let scale = 1;

  for (let index = 0; index < proposedSizes.length; index += 1) {
    const slot = MARKET_RADAR_LAYOUT[index] || MARKET_RADAR_LAYOUT[MARKET_RADAR_LAYOUT.length - 1];
    const centerX = (slot.x / 100) * gridWidth;
    const centerY = (slot.y / 100) * gridHeight;
    const maxRadiusForEdge = Math.max(
      36,
      Math.min(centerX - edgeGap, gridWidth - centerX - edgeGap, centerY - edgeGap, gridHeight - centerY - edgeGap)
    );
    scale = Math.min(scale, (maxRadiusForEdge * 2) / proposedSizes[index]);

    for (let compareIndex = index + 1; compareIndex < proposedSizes.length; compareIndex += 1) {
      const compareSlot = MARKET_RADAR_LAYOUT[compareIndex] || MARKET_RADAR_LAYOUT[MARKET_RADAR_LAYOUT.length - 1];
      const dx = ((slot.x - compareSlot.x) / 100) * gridWidth;
      const dy = ((slot.y - compareSlot.y) / 100) * gridHeight;
      const centerDistance = Math.hypot(dx, dy);
      const allowed = (centerDistance - bubbleGap) / ((proposedSizes[index] + proposedSizes[compareIndex]) / 2);
      scale = Math.min(scale, allowed);
    }
  }

  const clampedScale = Math.max(0.55, Math.min(scale, 1));

  return proposedSizes.map((size) => Math.max(72, Math.round(size * clampedScale)));
}

function renderMarketRadar() {
  const grid = document.getElementById('marketRadarGrid');
  if (!grid) return;

  const items = buildMarketRadarItems();
  renderMarketRadarStats(items);

  if (!items.length) {
    grid.innerHTML = '<div class="market-radar-empty">Market Radar will populate as watchlist and scanner data come online.</div>';
    return;
  }

  const bubbleSizes = getMarketRadarBubbleSizes(items, grid);

  grid.innerHTML = items.map((item, index) => {
    const slot = MARKET_RADAR_LAYOUT[index] || MARKET_RADAR_LAYOUT[MARKET_RADAR_LAYOUT.length - 1];
    const size = bubbleSizes[index] || 96;
    const changeText = item.expectedMovePct ? `${item.expectedMovePct.toFixed(1)}% exp move` : (item.changePct != null ? `${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(1)}%` : `${item.sourceCount || 1} src`);
    const biasText = item.direction || (item.sourceCount > 1 ? `${item.sourceCount} sources` : 'Watch');
    const featuredClass = index === 0 ? ' is-featured' : '';
    const bubbleTitle = `${item.ticker}${item.catalyst ? ` — ${item.catalyst}` : ''}`;

    return `
      <button
        class="market-radar-bubble${featuredClass}"
        type="button"
        data-tone="${escapeHtml(item.tone)}"
        style="left:${slot.x}%;top:${slot.y}%;width:${size}px;height:${size}px;"
        title="${escapeHtml(bubbleTitle)}"
        onclick="openTickerDetailModal('${escapeHtml(item.ticker)}')"
      >
        <span class="market-radar-symbol">${escapeHtml(item.ticker)}</span>
        <span class="market-radar-bias">${escapeHtml(biasText)}</span>
        <span class="market-radar-meta">${escapeHtml(changeText)}</span>
      </button>
    `;
  }).join('');
}

function getTopTradeHighlightStyle(pick = {}) {
  const score = Number(pick.score || 0);
  const confidence = Number(pick.confidence || 0);
  const normalized = Math.max(0, Math.min(1, ((score / 100) * 0.7) + ((confidence / 10) * 0.3)));
  const useGoldPalette = confidence >= 9;

  const borderAlpha = (0.12 + normalized * 0.42).toFixed(3);
  const glowAlpha = (0.06 + normalized * 0.28).toFixed(3);
  const washAlpha = (0.03 + normalized * 0.16).toFixed(3);
  const textMix = (58 + normalized * 30).toFixed(1);
  const accentMix = (42 + normalized * 48).toFixed(1);
  const labelAlpha = (0.26 + normalized * 0.34).toFixed(3);

  const borderColor = useGoldPalette ? '245, 158, 11' : '148, 163, 184';
  const glowColor = useGoldPalette ? '251, 191, 36' : '203, 213, 225';
  const washColor = useGoldPalette ? '255, 226, 138' : '226, 232, 240';
  const textColor = useGoldPalette ? '#fff4d6' : '#eef2f7';
  const accentBase = useGoldPalette ? '#fbbf24' : '#cbd5e1';
  const accentMixTarget = useGoldPalette ? '#22d3ee' : '#94a3b8';
  const labelColor = useGoldPalette ? '255, 216, 122' : '203, 213, 225';

  return [
    `--top-trade-border: rgba(${borderColor}, ${borderAlpha})`,
    `--top-trade-glow: rgba(${glowColor}, ${glowAlpha})`,
    `--top-trade-wash: rgba(${washColor}, ${washAlpha})`,
    `--top-trade-text: color-mix(in srgb, ${textColor} ${textMix}%, white)`,
    `--top-trade-accent: color-mix(in srgb, ${accentBase} ${accentMix}%, ${accentMixTarget})`,
    `--top-trade-label: rgba(${labelColor}, ${labelAlpha})`,
  ].join(';');
}

function renderTopTradeToday() {
  const summary = document.getElementById('topTradeSummary');
  const grid = document.getElementById('topTradeGrid');
  const meta = document.getElementById('topTradeMeta');
  if (!summary || !grid || !meta) return;

  if (TOP_TRADE_TODAY.loading) {
    meta.textContent = 'Ranking today\'s best options setups...';
    summary.innerHTML = '';
    grid.innerHTML = `
      <div class="top-trade-loading" role="status" aria-live="polite">
        <span class="top-trade-loading-horse" aria-hidden="true"></span>
        <div class="top-trade-loading-copy">
          <span class="top-trade-loading-title">Running daily setup engine...</span>
          <span class="top-trade-loading-subtitle">Scanning market structure, options flow, and momentum leaders.</span>
        </div>
      </div>
    `;
    return;
  }

  if (TOP_TRADE_TODAY.error) {
    meta.textContent = 'Top trade engine unavailable';
    summary.innerHTML = '';
    grid.innerHTML = `<div class="top-trade-empty">${escapeHtml(TOP_TRADE_TODAY.error)}</div>`;
    return;
  }

  const generatedLabel = TOP_TRADE_TODAY.generatedAt
    ? new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      }).format(new Date(TOP_TRADE_TODAY.generatedAt * 1000))
    : '';

  meta.textContent = TOP_TRADE_TODAY.marketDate
    ? `${TOP_TRADE_TODAY.marketDate} · ${TOP_TRADE_TODAY.sessionLabel || 'U.S. session'} · Updated ${generatedLabel || 'just now'}`
    : 'Daily setup engine';

  const avoidText = TOP_TRADE_TODAY.namesToAvoid?.length
    ? TOP_TRADE_TODAY.namesToAvoid.join(', ')
    : 'None with clear liquidity issues yet';
  const macroText = TOP_TRADE_TODAY.macroRisks?.length
    ? TOP_TRADE_TODAY.macroRisks.slice(0, 2).join(' · ')
    : 'No major scheduled macro risk in the feed';

  summary.innerHTML = `
    <div class="top-trade-summary-card">
      <span class="top-trade-summary-label">Best Overall</span>
      <div class="top-trade-summary-value">${escapeHtml(TOP_TRADE_TODAY.bestOverallPick || 'No trade')}</div>
    </div>
    <div class="top-trade-summary-card">
      <span class="top-trade-summary-label">Session Type</span>
      <div class="top-trade-summary-value">${escapeHtml(TOP_TRADE_TODAY.sessionType || 'Waiting on live data')}</div>
    </div>
    <div class="top-trade-summary-card">
      <span class="top-trade-summary-label">Choppy Day Warning</span>
      <div class="top-trade-summary-value ${TOP_TRADE_TODAY.choppyDayWarning ? 'warning' : ''}">${TOP_TRADE_TODAY.choppyDayWarning ? 'Yes' : 'No'}</div>
    </div>
    <div class="top-trade-summary-card top-trade-summary-card-danger">
      <span class="top-trade-summary-label">Names To Avoid</span>
      <div class="top-trade-summary-value">${escapeHtml(avoidText)}</div>
    </div>
    <div class="top-trade-summary-card" style="grid-column: 1 / -1;">
      <span class="top-trade-summary-label">Today\'s Key Macro Risks</span>
      <div class="top-trade-summary-value">${escapeHtml(macroText)}</div>
    </div>
  `;

  if (!TOP_TRADE_TODAY.picks?.length) {
    grid.innerHTML = `<div class="top-trade-empty">${escapeHtml(TOP_TRADE_TODAY.summary || 'No clean setups right now. Do not force trades.')}</div>`;
    return;
  }

  grid.innerHTML = TOP_TRADE_TODAY.picks.slice(0, 4).map((pick, index) => {
    const keyLevels = [
      pick.keyLevels?.support?.length ? `S: ${pick.keyLevels.support.join(' / ')}` : '',
      pick.keyLevels?.resistance?.length ? `R: ${pick.keyLevels.resistance.join(' / ')}` : '',
      pick.keyLevels?.trigger != null ? `Trigger: ${pick.keyLevels.trigger}` : '',
    ].filter(Boolean).join('<br>');
    const targets = Array.isArray(pick.profitTargets) && pick.profitTargets.length
      ? pick.profitTargets.join(' / ')
      : 'Trail once paid';
    const directionClass = String(pick.direction || '').toLowerCase();
    const highlightStyle = getTopTradeHighlightStyle(pick);
    const bottomLine = pick.bottomLine || pick.summary || pick.why || '—';

    return `
      <article class="top-trade-card top-trade-card-highlight" style="${highlightStyle}" tabindex="0">
        <div class="top-trade-rank-row">
          <span class="top-trade-rank-badge ${index === 0 ? 'is-top' : ''}">${index === 0 ? 'Top Pick #1' : `Top Pick #${index + 1}`}</span>
        </div>
        <div class="top-trade-card-header">
          <div class="top-trade-card-left">
            <span class="top-trade-ticker">${escapeHtml(pick.ticker)}</span>
            <span class="top-trade-direction ${escapeHtml(directionClass)}">${escapeHtml(pick.direction)}</span>
            <span class="top-trade-setup">${escapeHtml(pick.setupType || 'Setup')}</span>
          </div>
          <div class="top-trade-confidence">
            <span class="top-trade-confidence-score">${escapeHtml(String(pick.confidence || '—'))}/10</span>
            <span class="top-trade-confidence-label">Confidence</span>
          </div>
        </div>
        <div class="top-trade-body">
          <p class="top-trade-copy">${escapeHtml(pick.why || '')}</p>
          <div class="top-trade-level-grid">
            <div class="top-trade-level">
              <span class="top-trade-level-label">Key Levels</span>
              <div class="top-trade-level-value">${keyLevels || 'Waiting on clean levels'}</div>
            </div>
            <div class="top-trade-level">
              <span class="top-trade-level-label">Trigger / Invalidation</span>
              <div class="top-trade-level-value">${escapeHtml(pick.triggerToEnter || 'Wait') }<br>${escapeHtml(pick.stopInvalidation || '')}</div>
            </div>
          </div>
          <div class="top-trade-contract-grid">
            <div class="top-trade-contract">
              <span class="top-trade-contract-label">Targets</span>
              <div class="top-trade-contract-value">${escapeHtml(targets)}</div>
            </div>
            <div class="top-trade-contract">
              <span class="top-trade-contract-label">Best Contract</span>
              <div class="top-trade-contract-value">${escapeHtml(pick.bestContractIdea?.strike || '—')}<br>${escapeHtml(pick.bestContractIdea?.expiry || '—')}</div>
            </div>
            <div class="top-trade-contract">
              <span class="top-trade-contract-label">Delta / Risk</span>
              <div class="top-trade-contract-value">${escapeHtml(pick.bestContractIdea?.deltaPreference || '—')}<br>${escapeHtml(pick.riskLevel || '—')}</div>
            </div>
          </div>
          <div class="top-trade-footer-grid">
            <div class="top-trade-footer">
              <span class="top-trade-footer-label">What Could Ruin It</span>
              <div class="top-trade-footer-value">${escapeHtml(pick.ruinRisk || '—')}</div>
            </div>
            <div class="top-trade-footer" style="grid-column: span 2;">
              <span class="top-trade-footer-label">Bottom Line</span>
              <div class="top-trade-footer-value">${escapeHtml(bottomLine)}</div>
            </div>
          </div>
        </div>
      </article>
    `;
  }).join('');
}

function getAlertItems() {
  const alerts = [];
  const tradeAlerts = ALERT_STATE.items.slice(0, 2).map((item) => ({
    type: item.direction === 'LONG' ? 'macro' : 'today',
    text: `${item.ticker} ${item.direction} triggered at ${item.price} vs ${item.entry}`
  }));

  if (tradeAlerts.length) {
    alerts.push(...tradeAlerts);
  }
  const todayKey = new Intl.DateTimeFormat('en-CA', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date());
  const tomorrowDate = new Date();
  tomorrowDate.setDate(tomorrowDate.getDate() + 1);
  const tomorrowKey = new Intl.DateTimeFormat('en-CA', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(tomorrowDate);

  const todaysEvents = ECONOMIC_CALENDAR.events
    .filter((event) => event.dayKey === todayKey)
    .map((event) => ({
      type: 'today',
      text: `Today ${event.timeLabel}: ${event.title}`
    }));

  const tomorrowEvents = ECONOMIC_CALENDAR.events
    .filter((event) => event.dayKey === tomorrowKey)
    .map((event) => ({
      type: 'week',
      text: `Tomorrow ${event.timeLabel}: ${event.title}`
    }));

  if (todaysEvents.length) {
    alerts.push(...todaysEvents);
  }

  if (tomorrowEvents.length) {
    alerts.push(...tomorrowEvents);
  }

  if (!todaysEvents.length && !tomorrowEvents.length) {
    const nextEvent = ECONOMIC_CALENDAR.events[0];
    if (nextEvent) {
      alerts.push({
        type: 'today',
        text: `Next red-folder event ${nextEvent.dayLabelShort} ${nextEvent.timeLabel}: ${nextEvent.title}`
      });
    }
  }

  if (!alerts.length) {
    alerts.push({
      type: 'week',
      text: 'Waiting for live U.S. red-folder events for today and tomorrow.'
    });
  }

  return alerts.slice(0, 5);
}

function renderAlertBar() {
  const track = document.getElementById('alertBarTrack');
  if (!track) return;

  const items = getAlertItems();
  const hasRedFolderAlert = ECONOMIC_CALENDAR.events.length > 0;
  const bar = document.getElementById('alertBar');
  if (bar) bar.classList.toggle('alert-bar--red', hasRedFolderAlert);

  track.innerHTML = items.map((alert) => `
    <span class="alert-pill ${escapeHtml(alert.type)}">${escapeHtml(alert.text)}</span>
  `).join('');
}

function renderCalendar() {
  const tbody = document.getElementById('calendarBody');
  const meta = document.getElementById('calendarMeta');
  const events = ECONOMIC_CALENDAR.events;

  if (meta) {
    if (ECONOMIC_CALENDAR.error) {
      meta.textContent = `USD red folder only · ${ECONOMIC_CALENDAR.error}`;
    } else if (events.length > 0) {
      const weekLabel = getCalendarWeekLabel(events);
      const updatedLabel = ECONOMIC_CALENDAR.lastUpdated ? ` · Updated ${ECONOMIC_CALENDAR.lastUpdated}` : '';
      meta.textContent = `USD red folder only · ${weekLabel} · Times shown in ${ECONOMIC_CALENDAR.timezone}${updatedLabel}`;
    } else {
      meta.innerHTML = renderLoadingInline('Loading weekly events...', 'Building this week\'s red-folder calendar');
    }
  }

  if (events.length === 0) {
    tbody.innerHTML = `
      <tr class="${ECONOMIC_CALENDAR.error ? 'calendar-empty-row' : 'calendar-loading-row'}">
        <td colspan="7" class="${ECONOMIC_CALENDAR.error ? 'calendar-error' : ''}">
          ${ECONOMIC_CALENDAR.error ? escapeHtml(ECONOMIC_CALENDAR.error) : renderLoadingInline("Loading this week's red-folder events...", 'Pulling the live macro feed')}
        </td>
      </tr>
    `;
    renderAlertBar();
    return;
  }

  let lastDayKey = '';
  tbody.innerHTML = events.map((event) => {
    const showDivider = event.dayKey !== lastDayKey;
    lastDayKey = event.dayKey;

    return `
      ${showDivider ? `
        <tr class="calendar-day-divider">
          <td colspan="7"><span class="calendar-day-label">${escapeHtml(event.dayLabelLong)}</span></td>
        </tr>
      ` : ''}
      <tr>
        <td class="calendar-day-cell">${escapeHtml(event.dayLabelShort)}</td>
        <td class="calendar-time-cell">${escapeHtml(event.timeLabel)}</td>
        <td><span class="calendar-currency">${escapeHtml(event.country || '---')}</span></td>
        <td>
          <div class="calendar-event-title">
            <span class="calendar-event-name">${escapeHtml(event.title)}</span>
            <span class="calendar-event-detail"><span class="calendar-impact">Red Folder</span></span>
          </div>
        </td>
        <td class="calendar-value">${escapeHtml(event.forecast || '—')}</td>
        <td class="calendar-value">${escapeHtml(event.previous || '—')}</td>
        <td class="calendar-value calendar-value-actual">${escapeHtml(event.actual || '—')}</td>
      </tr>
    `;
  }).join('');

  renderAlertBar();
}

function getCalendarWeekLabel(events) {
  if (events.length === 0) return 'This week';
  const first = events[0].date;
  const last = events[events.length - 1].date;
  const monthFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    month: 'short',
    day: 'numeric'
  });
  return `Week of ${monthFormatter.format(first)}-${monthFormatter.format(last)}`;
}

function buildFallbackCalendarEvents() {
  const baseDate = new Date();
  return DASHBOARD_DATA.calendar.map((row, index) => {
    const fallbackDate = new Date(baseDate);
    fallbackDate.setHours(8 + index, 30, 0, 0);
    return formatEconomicEvent({
      title: row.event,
      country: 'USD',
      date: fallbackDate.toISOString(),
      impact: 'High',
      forecast: '',
      previous: row.prior,
      actual: ''
    });
  }).filter(Boolean);
}

function extractCalendarPayload(rawText) {
  const trimmed = rawText.trim();
  if (trimmed.startsWith('[')) return trimmed;

  const marker = 'Markdown Content:';
  if (trimmed.includes(marker)) {
    return trimmed.slice(trimmed.indexOf(marker) + marker.length).trim();
  }

  const arrayStart = trimmed.indexOf('[{');
  if (arrayStart >= 0) return trimmed.slice(arrayStart).trim();

  throw new Error('Calendar payload was not JSON.');
}

function formatEconomicEvent(rawEvent) {
  if (!rawEvent || rawEvent.impact !== 'High' || rawEvent.country !== ECONOMIC_CALENDAR.country || !rawEvent.date) {
    return null;
  }

  const eventDate = new Date(rawEvent.date);
  if (Number.isNaN(eventDate.getTime())) return null;

  const dayLongFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    weekday: 'long',
    month: 'short',
    day: 'numeric'
  });
  const dayShortFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    weekday: 'short'
  });
  const timeFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    hour: 'numeric',
    minute: '2-digit'
  });
  const dayKeyFormatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });

  return {
    title: rawEvent.title || 'Unnamed event',
    country: rawEvent.country || '',
    forecast: rawEvent.forecast || '',
    previous: rawEvent.previous || '',
    actual: rawEvent.actual || '',
    impact: rawEvent.impact,
    date: eventDate,
    dayKey: dayKeyFormatter.format(eventDate),
    dayLabelLong: dayLongFormatter.format(eventDate),
    dayLabelShort: dayShortFormatter.format(eventDate),
    timeLabel: timeFormatter.format(eventDate)
  };
}

async function fetchEconomicCalendar() {
  const fetchOptions = {
    headers: {
      'Accept': 'application/json, text/plain;q=0.9, */*;q=0.8'
    }
  };

  for (const source of ECONOMIC_CALENDAR.sources) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 4500);
      const response = await fetch(source, {
        ...fetchOptions,
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }

      const responseText = await response.text();
      const jsonPayload = extractCalendarPayload(responseText);
      const parsed = JSON.parse(jsonPayload);
      const events = parsed
        .map(formatEconomicEvent)
        .filter(Boolean)
        .sort((a, b) => a.date - b.date);

      if (events.length === 0) {
        throw new Error('No high-impact events were returned.');
      }

      ECONOMIC_CALENDAR.events = events;
      ECONOMIC_CALENDAR.error = '';
      ECONOMIC_CALENDAR.lastUpdated = new Intl.DateTimeFormat('en-US', {
        timeZone: ECONOMIC_CALENDAR.timezone,
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      }).format(new Date());
      renderCalendar();
      return;
    } catch (error) {
      ECONOMIC_CALENDAR.error = `Live feed unavailable from ${new URL(source).hostname}`;
    }
  }

  ECONOMIC_CALENDAR.events = buildFallbackCalendarEvents();
  ECONOMIC_CALENDAR.error = 'Live weekly feed unavailable. Showing dashboard fallback events.';
  ECONOMIC_CALENDAR.lastUpdated = '';
  renderCalendar();
}

function renderIndexCards() {
  const grid = document.getElementById('indexGrid');
  grid.innerHTML = DASHBOARD_DATA.indexes.map((idx, i) => `
    <div class="index-card" style="animation-delay: ${0.1 + i * 0.05}s" data-hover-ticker="${escapeHtml(idx.ticker)}">
      <div class="index-card-header">
        <div class="index-ticker-link" onclick="window.open('${getTradingViewUrl(idx.ticker)}', '_blank')" title="Open ${idx.ticker} on TradingView">
          <div class="index-ticker">${escapeHtml(idx.ticker)} <span style="font-size:0.65rem; color:var(--text-muted);">↗</span></div>
          <div class="index-name">${escapeHtml(idx.name)}</div>
        </div>
        <span class="badge badge-bias ${getBiasClass(idx.bias)}">${escapeHtml(idx.bias)}</span>
      </div>

      <div style="display:flex; align-items:baseline; gap:10px; margin-bottom:8px;">
        <span class="index-price glow-hover">${formatPrice(idx.price)}</span>
        <span class="index-change ${getChangeClass(idx.change)}">${formatChange(idx.change)}</span>
      </div>

      <div class="index-metrics">
        <div class="metric-item">
          <span class="metric-label">RSI (14)</span>
          <span class="metric-value ${getRsiClass(idx.rsi)} glow-hover">${idx.rsi}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">ATR</span>
          <span class="metric-value glow-hover">${idx.atr} <span style="color:var(--text-muted); font-size:0.7rem;">(${idx.atrPct}%)</span></span>
        </div>
        <div class="metric-item">
          <span class="metric-label">Exp Move</span>
          <span class="metric-value glow-hover" style="color:var(--amber);">${escapeHtml(idx.expectedMove)}</span>
        </div>
      </div>

      <div class="index-levels">
        <div class="level-row">
          <span class="level-label">Support</span>
          <span class="level-values" style="color:var(--green);">${idx.support.join(' / ')}</span>
        </div>
        <div class="level-row">
          <span class="level-label">Resistance</span>
          <span class="level-values" style="color:var(--red);">${idx.resistance.join(' / ')}</span>
        </div>
      </div>

      <div class="index-triggers">
        <div class="trigger trigger-bull">▲ ${escapeHtml(idx.bullTrigger)}</div>
        <div class="trigger trigger-bear">▼ ${escapeHtml(idx.bearTrigger)}</div>
      </div>

      <div class="chart-container" onclick="window.open('${getTradingViewUrl(idx.ticker)}', '_blank')" title="Open ${idx.ticker} on TradingView">
        <canvas class="sparkline-canvas" data-ticker="${idx.ticker}"></canvas>
      </div>

      <div class="index-strategy">${escapeHtml(idx.strategy)}</div>
    </div>
  `).join('');
}

function renderTickerCards() {
  const grid = document.getElementById('tickerGrid');
  if (!DASHBOARD_DATA.tickers.length) {
    grid.innerHTML = '<div class="ticker-loading-state">Fetching best intraday tickers from live market data&hellip;</div>';
    return;
  }
  grid.innerHTML = DASHBOARD_DATA.tickers.map((t, i) => `
    <div class="ticker-card ${t.star ? 'star-pick' : ''}" style="animation-delay: ${0.15 + i * 0.04}s" data-hover-ticker="${escapeHtml(t.ticker)}">
      ${t.star ? '<div class="star-icon">★</div>' : ''}

      <div class="ticker-rank">#${t.rank}</div>

      <div class="ticker-header ticker-header-link" onclick="window.open('${getTradingViewUrl(t.ticker)}', '_blank')" title="Open ${t.ticker} chart on TradingView">
        <span class="ticker-symbol">${escapeHtml(t.ticker)}</span>
        <span class="ticker-name">${escapeHtml(t.name)}</span>
        <span style="font-size:0.7rem; color:var(--text-muted); margin-left:auto;">↗</span>
      </div>

      <div class="ticker-prices">
        <div class="price-group">
          <span class="price-label">Close</span>
          <span class="price-value glow-hover">${formatPrice(t.price)}</span>
          <span class="price-change ${getChangeClass(t.friChange)}">${formatChange(t.friChange)}</span>
        </div>
        <div class="price-group">
          <span class="price-label">After Hours</span>
          <span class="price-value glow-hover" style="font-size:0.95rem;">${formatPrice(t.ahPrice)}</span>
          <span class="price-change ${getChangeClass(t.ahChange)}">${formatChange(t.ahChange)}</span>
        </div>
      </div>

      <div class="ticker-badges">
        <span class="badge badge-bias ${getBiasClass(t.bias)}">${escapeHtml(t.bias)}</span>
        <span class="badge badge-strategy">${escapeHtml(t.strategy)}</span>
      </div>

      ${t.signalScore != null ? `<div class="signal-score-row">${renderSignalBadge(t.signalScore)}</div>` : ''}

      <div class="chart-container" onclick="window.open('${getTradingViewUrl(t.ticker)}', '_blank')" title="Open ${t.ticker} on TradingView">
        <canvas class="sparkline-canvas" data-ticker="${t.ticker}"></canvas>
      </div>

      <div class="ticker-compact-stats">
        <div class="ticker-compact-stat">
          <span class="ticker-compact-label">RSI</span>
          <span class="ticker-compact-value ${getRsiClass(t.rsi)}">${t.rsi}</span>
        </div>
        <div class="ticker-compact-stat">
          <span class="ticker-compact-label">ATR</span>
          <span class="ticker-compact-value">${t.atr}</span>
        </div>
        <div class="ticker-compact-stat">
          <span class="ticker-compact-label">Move</span>
          <span class="ticker-compact-value">${escapeHtml(t.expectedMove)}</span>
        </div>
      </div>

      <div class="ticker-levels-compact">
        <div class="ticker-levels-row">
          <span class="ticker-levels-label">Support</span>
          <span class="ticker-levels-value support">${t.support.slice(0, 2).join(' / ')}</span>
        </div>
        <div class="ticker-levels-row">
          <span class="ticker-levels-label">Resistance</span>
          <span class="ticker-levels-value resistance">${t.resistance.slice(0, 2).join(' / ')}</span>
        </div>
      </div>
    </div>
  `).join('');
}

const TOP_WATCH_SOURCE_COLORS = {
  StockTwits:  { bg: 'rgba(105,80,255,0.18)', color: '#a78bfa', border: 'rgba(105,80,255,0.35)' },
  MarketWatch: { bg: 'rgba(34,211,238,0.12)', color: '#22d3ee', border: 'rgba(34,211,238,0.3)'  },
  Barchart:    { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.3)'  },
  Finviz:      { bg: 'rgba(52,211,153,0.12)', color: '#34d399', border: 'rgba(52,211,153,0.3)'  },
};

function renderTopWatchSourceBadge(source) {
  const c = TOP_WATCH_SOURCE_COLORS[source] || { bg: 'rgba(255,255,255,0.08)', color: 'var(--text-muted)', border: 'rgba(255,255,255,0.15)' };
  return `<span class="tw-source-badge" style="background:${c.bg};color:${c.color};border-color:${c.border};">${escapeHtml(source)}</span>`;
}

function renderTopWatchHeat(count) {
  if (count >= 4) return { label: '4/4', cls: 'tw-heat-max',  title: 'Mentioned on all 4 sources' };
  if (count === 3) return { label: '3/4', cls: 'tw-heat-high', title: 'Mentioned on 3 of 4 sources' };
  return               { label: '2/4', cls: 'tw-heat-mid',  title: 'Mentioned on 2 of 4 sources' };
}

function renderTopWatch() {
  const tbody  = document.getElementById('topWatchBody');
  const meta   = document.getElementById('topWatchMeta');
  const srcBar = document.getElementById('topWatchSourceBar');
  if (!tbody) return;

  // Source status bar
  const sources = ['StockTwits', 'MarketWatch', 'Barchart', 'Finviz'];
  if (srcBar) {
    if (Object.keys(TOP_WATCH.sourceStatus).length) {
      srcBar.innerHTML = sources.map(s => {
        const ok = TOP_WATCH.sourceStatus[s];
        const c  = TOP_WATCH_SOURCE_COLORS[s];
        return `<span class="tw-src-status ${ok ? 'tw-src-ok' : 'tw-src-err'}" style="${ok ? `color:${c.color}` : ''}">${ok ? '●' : '○'} ${s}</span>`;
      }).join('');
    } else {
      srcBar.innerHTML = '';
    }
  }

  if (TOP_WATCH.loading) {
    tbody.innerHTML = renderLoadingRow(8, 'Scanning StockTwits, MarketWatch, Barchart, and Finviz...', 'Looking for cross-source agreement');
    if (meta) meta.innerHTML = renderLoadingInline('Scanning sources...', 'Waiting for cross-source matches');
    return;
  }

  if (TOP_WATCH.error) {
    tbody.innerHTML = `<tr class="top-watch-loading-row"><td colspan="8">${escapeHtml(TOP_WATCH.error)}</td></tr>`;
    if (meta) meta.textContent = TOP_WATCH.error;
    return;
  }

  const items = TOP_WATCH.topWatch;

  if (meta) {
    meta.textContent = items.length
      ? `${items.length} cross-source ticker${items.length !== 1 ? 's' : ''} · Updated ${TOP_WATCH.updatedAt}`
      : `No cross-source matches · Updated ${TOP_WATCH.updatedAt}`;
  }

  if (!items.length) {
    tbody.innerHTML = '<tr class="top-watch-loading-row"><td colspan="8">No tickers found on 2+ sources right now.</td></tr>';
    return;
  }

  tbody.innerHTML = items.map(w => {
    const heat = renderTopWatchHeat(w.sourceCount);

    const priceHtml = w.price != null
      ? `<span style="color:var(--text-bright);font-weight:700;">${formatPrice(w.price)}</span>`
      : '<span style="color:var(--text-muted);">—</span>';

    const changeHtml = w.changePct != null
      ? `<span class="${getChangeClass(w.changePct)}">${formatChange(w.changePct)}</span>`
      : '<span style="color:var(--text-muted);">—</span>';

    // Pull signal data from DASHBOARD_DATA if ticker exists there
    const existing = (DASHBOARD_DATA.tickers || []).find(t => t.ticker === w.ticker)
      || (DASHBOARD_DATA.watchlist || []).find(t => t.ticker === w.ticker);
    const signalHtml = existing?.signalScore != null ? renderSignalBadge(existing.signalScore) : '—';
    const relHtml    = existing?.relStrength  != null ? renderWatchlistRelStrength(existing.relStrength) : '—';
    const dirHtml    = existing?.direction
      ? `<span class="${existing.direction === 'LONG' ? 'direction-long' : 'direction-short'}">${escapeHtml(existing.direction)}</span>`
      : (existing?.bias
          ? `<span class="badge badge-bias ${getBiasClass(existing.bias)}" style="font-size:0.7rem;">${escapeHtml(existing.bias)}</span>`
          : '<span style="color:var(--text-muted);">—</span>');

    const otm = w.otmSpread;
    const otmHtml = otm?.spreadLabel
      ? `<span class="tw-otm-spread" title="${escapeHtml(otm.optionType === 'C' ? 'OTM Call' : 'OTM Put')} ${escapeHtml(String(otm.strike ?? ''))} exp ${escapeHtml(otm.expirationDate ?? '')}">
           ${escapeHtml(otm.spreadLabel)}&nbsp;<span class="tw-otm-type ${otm.optionType === 'C' ? 'tw-otm-call' : 'tw-otm-put'}">${escapeHtml(otm.optionType)}</span>
         </span>`
      : '<span style="color:var(--text-muted);">—</span>';

    const pcr = w.putCallRatio;
    let pcrHtml = '<span style="color:var(--text-muted);">—</span>';
    if (pcr?.label && pcr.label !== 'n/a') {
      const pcrCls = pcr.leader === 'calls' ? 'tw-pcr-calls'
                   : pcr.leader === 'puts'  ? 'tw-pcr-puts'
                   : 'tw-pcr-balanced';
      const pcrTitle = `Calls: ${(pcr.callVolume ?? 0).toLocaleString()}  Puts: ${(pcr.putVolume ?? 0).toLocaleString()}`;
      pcrHtml = `<span class="tw-pcr ${pcrCls}" title="${escapeHtml(pcrTitle)}">${escapeHtml(pcr.label)}</span>`;
    }

    return `
      <tr class="top-watch-row"
          role="button" tabindex="0"
          onclick="openTickerDetailModal('${escapeHtml(w.ticker)}')"
          onkeydown="if(event.key==='Enter')openTickerDetailModal('${escapeHtml(w.ticker)}')"
          title="Open ${escapeHtml(w.ticker)} detail">
        <td>
          <span class="tw-ticker">${escapeHtml(w.ticker)}</span>
          <span class="tw-heat ${heat.cls}" title="${heat.title}">${heat.label}</span>
        </td>
        <td>${priceHtml}</td>
        <td>${changeHtml}</td>
        <td>${signalHtml}</td>
        <td>${relHtml}</td>
        <td>${dirHtml}</td>
        <td>${otmHtml}</td>
        <td>${pcrHtml}</td>
      </tr>
    `;
  }).join('');
}

function renderWatchlist() {
  const tbody = document.getElementById('watchlistBody');
  tbody.innerHTML = DASHBOARD_DATA.watchlist.map(w => `
    <tr
      class="watchlist-row"
      role="button"
      tabindex="0"
      onclick="openTickerDetailModal('${escapeHtml(w.ticker)}')"
      onkeydown="handleWatchlistKeydown(event, '${escapeHtml(w.ticker)}')"
      title="Open ${escapeHtml(w.ticker)} detail"
      data-hover-ticker="${escapeHtml(w.ticker)}"
    >
      <td style="color: var(--text-muted); font-weight:700;">${w.rank}</td>
      <td style="color: var(--text-bright); font-weight:700;">${escapeHtml(w.ticker)}</td>
      <td>${w.signalScore != null ? renderSignalBadge(w.signalScore) : '—'}</td>
      <td>${renderWatchlistRelStrength(w.relStrength)}</td>
      <td>${renderWatchlistPutCallRatio(w.ticker)}</td>
      <td class="${w.direction === 'LONG' ? 'direction-long' : 'direction-short'}">${escapeHtml(w.direction)}</td>
      <td>${escapeHtml(w.entry)}</td>
      <td>${escapeHtml(w.target)}</td>
      <td style="color: var(--red);">${escapeHtml(w.stop)}</td>
      <td style="color: var(--text-secondary);">${escapeHtml(w.catalyst)}</td>
    </tr>
  `).join('');
}

function renderWatchlistRelStrength(rel) {
  if (rel == null) return '<span style="color: var(--text-muted);">—</span>';
  const sign = rel >= 0 ? '+' : '';
  const color = rel > 0.5 ? 'var(--green)' : rel < -0.5 ? 'var(--red)' : 'var(--text-muted)';
  const label = rel > 0.5 ? 'Outperform' : rel < -0.5 ? 'Underperform' : 'In-line';
  return `
    <div style="display:inline-flex;flex-direction:column;gap:2px;min-width:72px;">
      <span style="color:${color};font-weight:700;">${sign}${rel.toFixed(1)}%</span>
      <span style="font-size:0.66rem;text-transform:uppercase;letter-spacing:0.7px;color:${color};">${label}</span>
    </div>
  `;
}

function renderWatchlistPutCallRatio(ticker) {
  const row = (OPTIONS_FLOW.atmSpreads || []).find((item) => item.ticker === ticker);
  const ratio = row?.putCallRatio;
  if (!ratio) return '<span style="color: var(--text-muted);">—</span>';

  const leaderClass = ratio.leader || 'balanced';
  const leaderText = leaderClass === 'calls'
    ? 'Calls'
    : leaderClass === 'puts'
      ? 'Puts'
      : 'Balanced';
  const tooltip = `Calls ${Number(ratio.callVolume || 0).toLocaleString()} vs puts ${Number(ratio.putVolume || 0).toLocaleString()} volume`;

  return `
    <div class="watchlist-pcr ${leaderClass}" title="${escapeHtml(tooltip)}">
      <span class="watchlist-pcr-ratio">${escapeHtml(ratio.label || 'n/a')}</span>
      <span class="watchlist-pcr-leader">${escapeHtml(leaderText)}</span>
    </div>
  `;
}

function renderThemes() {
  const list = document.getElementById('themesList');
  list.innerHTML = DASHBOARD_DATA.themes.map(t => 
    `<li>${escapeHtml(t)}</li>`
  ).join('');
}

function renderOptionsFlowRows(rows, type) {
  if (!rows.length) {
    return `<tr class="options-flow-loading"><td colspan="5">No options activity available.</td></tr>`;
  }

  if (type === 'unusual') {
    return rows.map((row) => `
      <tr>
        <td style="color: var(--text-bright); font-weight:700;">${escapeHtml(row.baseSymbol)}</td>
        <td>
          <div class="options-flow-contract">
            <span class="options-flow-contract-main">${escapeHtml(row.contract)}</span>
            <span class="options-flow-contract-sub">${escapeHtml(row.expirationDate)}</span>
          </div>
        </td>
        <td>${escapeHtml(row.premium)}</td>
        <td>${escapeHtml(row.tradeSize)}</td>
        <td class="options-flow-bias ${String(row.sentiment || '').toLowerCase()}">${escapeHtml(row.sentiment)}</td>
      </tr>
    `).join('');
  }

  return rows.map((row) => `
    <tr>
      <td style="color: var(--text-bright); font-weight:700;">${escapeHtml(row.baseSymbol)}</td>
      <td>
        <div class="options-flow-contract">
          <span class="options-flow-contract-main">${escapeHtml(row.contract)}</span>
          <span class="options-flow-contract-sub">${escapeHtml(row.expirationDate)}</span>
        </div>
      </td>
      <td>${escapeHtml(row.lastPrice)}</td>
      <td>${escapeHtml(row.volume)}</td>
      <td>${escapeHtml(row.openInterest)}</td>
    </tr>
  `).join('');
}

function renderAtmSpreadRows(rows, maxSpreadDollars) {
  if (!rows.length) {
    return `<tr class="options-flow-loading"><td colspan="6">No ATM spread data available.</td></tr>`;
  }

  return rows.map((row) => {
    const statusClass = row.isWide ? 'wide' : 'ok';
    const statusText = row.isWide ? `Avoid > $${maxSpreadDollars.toFixed(2)}` : 'Tradeable';
    const pcrHtml = renderWatchlistPutCallRatio(row.ticker);

    return `
      <tr>
        <td style="color: var(--text-bright); font-weight:700;">${escapeHtml(row.ticker)}</td>
        <td>${escapeHtml(row.underlyingPrice || '—')}</td>
        <td>
          <div class="options-spread-cell">
            <span class="options-spread-main">${escapeHtml(row.call.spreadLabel)}</span>
            <span class="options-spread-sub">${escapeHtml(row.call.contract)} · ${escapeHtml(row.call.expirationDate)}</span>
          </div>
        </td>
        <td>
          <div class="options-spread-cell">
            <span class="options-spread-main">${escapeHtml(row.put.spreadLabel)}</span>
            <span class="options-spread-sub">${escapeHtml(row.put.contract)} · ${escapeHtml(row.put.expirationDate)}</span>
          </div>
        </td>
        <td>${pcrHtml}</td>
        <td class="options-spread-status ${statusClass}">${escapeHtml(statusText)}</td>
      </tr>
    `;
  }).join('');
}

function renderOptionsFlow() {
  const unusualBody = document.getElementById('unusualOptionsBody');
  const mostActiveBody = document.getElementById('mostActiveOptionsBody');
  const atmSpreadBody = document.getElementById('atmSpreadBody');
  const meta = document.getElementById('optionsFlowMeta');
  const ratio = document.getElementById('optionsFlowRatio');

  if (OPTIONS_FLOW.loading) {
    unusualBody.innerHTML = renderLoadingRow(5, 'Loading Barchart options activity...', 'Checking unusual and most-active contracts');
    mostActiveBody.innerHTML = renderLoadingRow(5, 'Loading Barchart options activity...', 'Checking unusual and most-active contracts');
    atmSpreadBody.innerHTML = renderLoadingRow(6, 'Loading Barchart ATM spreads...', 'Checking tradable contracts and spread quality');
    meta.innerHTML = renderLoadingInline('Loading Barchart options activity...', 'Syncing flow, liquidity, and ratio data');
    if (ratio) {
      ratio.className = 'options-flow-ratio';
      ratio.innerHTML = renderLoadingInline('Loading put/call ratio...');
    }
    return;
  }

  if (OPTIONS_FLOW.error) {
    unusualBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">${escapeHtml(OPTIONS_FLOW.error)}</td></tr>`;
    mostActiveBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">${escapeHtml(OPTIONS_FLOW.error)}</td></tr>`;
    atmSpreadBody.innerHTML = `<tr class="options-flow-loading"><td colspan="6">${escapeHtml(OPTIONS_FLOW.error)}</td></tr>`;
    meta.textContent = 'Barchart feed unavailable';
    if (ratio) {
      ratio.className = 'options-flow-ratio';
      ratio.textContent = 'Put/call ratio unavailable';
    }
    return;
  }

  atmSpreadBody.innerHTML = renderAtmSpreadRows(OPTIONS_FLOW.atmSpreads, OPTIONS_FLOW.maxSpreadDollars);
  unusualBody.innerHTML = renderOptionsFlowRows(OPTIONS_FLOW.unusual, 'unusual');
  mostActiveBody.innerHTML = renderOptionsFlowRows(OPTIONS_FLOW.mostActive, 'active');
  if (ratio) {
    const flowRatio = OPTIONS_FLOW.putCallRatio || {};
    const leader = flowRatio.leader || 'balanced';
    const ratioLabel = typeof flowRatio.ratio === 'number'
      ? `Call/put ${flowRatio.ratio.toFixed(2)}:1`
      : 'Call/put n/a';
    ratio.className = `options-flow-ratio ${leader}`;
    ratio.textContent = `${ratioLabel} · ${flowRatio.summary || 'Put/call mix unavailable'}`;
  }
  meta.textContent = OPTIONS_FLOW.updatedAt
    ? `Source: Barchart · ATM liquidity threshold $${OPTIONS_FLOW.maxSpreadDollars.toFixed(2)} · Updated ${OPTIONS_FLOW.updatedAt}`
    : 'Source: Barchart';
}

async function fetchOptionsFlow(forceFresh = false) {
  OPTIONS_FLOW.loading = true;
  renderOptionsFlow();

  try {
    const query = buildTickerQuery();
    const separator = query ? '&' : '?';
    const source = forceFresh
      ? `/api/options-flow${query}${separator}fresh=1&t=${Date.now()}`
      : `/api/options-flow${query}`;
    const response = await fetch(source, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error('Options activity proxy unavailable.');
    }

    const payload = await response.json();
    OPTIONS_FLOW.unusual = payload.unusual || [];
    OPTIONS_FLOW.mostActive = payload.mostActive || [];
    OPTIONS_FLOW.atmSpreads = payload.atmSpreads || [];
    OPTIONS_FLOW.putCallRatio = payload.putCallRatio || null;
    OPTIONS_FLOW.maxSpreadDollars = typeof payload.maxSpreadDollars === 'number' ? payload.maxSpreadDollars : 0.15;
    OPTIONS_FLOW.error = '';
    OPTIONS_FLOW.loading = false;
    OPTIONS_FLOW.updatedAt = payload.updatedAt
      ? new Intl.DateTimeFormat('en-US', {
          hour: 'numeric',
          minute: '2-digit'
        }).format(new Date(payload.updatedAt * 1000))
      : '';
  } catch (error) {
    OPTIONS_FLOW.unusual = [];
    OPTIONS_FLOW.mostActive = [];
    OPTIONS_FLOW.atmSpreads = [];
    OPTIONS_FLOW.putCallRatio = null;
    OPTIONS_FLOW.maxSpreadDollars = 0.15;
    OPTIONS_FLOW.loading = false;
    OPTIONS_FLOW.error = 'Use server.py to load live Barchart options activity.';
    OPTIONS_FLOW.updatedAt = '';
  }

  renderOptionsFlow();
  renderWatchlist();
  renderMarketRadar();
  evaluateTradeAlerts();
}

async function fetchAppVersion() {
  try {
    const r = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return;
    const { version } = await r.json();
    const el = document.getElementById('navVersion');
    if (el && version) el.textContent = `v${version}`;
  } catch (_) {}
}

async function fetchTopWatch(forceFresh = false) {
  TOP_WATCH.loading = true;
  renderTopWatch();

  try {
    const sep = forceFresh ? `?fresh=1&t=${Date.now()}` : '';
    const response = await fetch(`/api/top-watch${sep}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Top watch endpoint unavailable.');

    const payload = await response.json();
    TOP_WATCH.topWatch     = payload.topWatch     || [];
    TOP_WATCH.sourceStatus = payload.sourceStatus || {};
    TOP_WATCH.updatedAt    = payload.updatedAt    || '';
    TOP_WATCH.error        = '';
    TOP_WATCH.loading      = false;
  } catch (error) {
    TOP_WATCH.topWatch     = [];
    TOP_WATCH.sourceStatus = {};
    TOP_WATCH.loading      = false;
    TOP_WATCH.error        = 'Run server.py to enable cross-source scanning.';
  }

  renderTopWatch();
  renderMarketRadar();
}

async function fetchTopTradeToday(forceFresh = false) {
  TOP_TRADE_TODAY.loading = true;
  renderTopTradeToday();

  try {
    const sep = forceFresh ? `?fresh=1&t=${Date.now()}` : '';
    const response = await fetch(`/api/top-trade-today${sep}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Daily setup engine unavailable.');

    const payload = await response.json();
    TOP_TRADE_TODAY.picks = payload.picks || [];
    TOP_TRADE_TODAY.bestOverallPick = payload.bestOverallPick || '';
    TOP_TRADE_TODAY.namesToAvoid = payload.namesToAvoid || [];
    TOP_TRADE_TODAY.macroRisks = payload.macroRisks || [];
    TOP_TRADE_TODAY.summary = payload.summary || '';
    TOP_TRADE_TODAY.sessionType = payload.sessionType || '';
    TOP_TRADE_TODAY.sessionLabel = payload.sessionLabel || '';
    TOP_TRADE_TODAY.marketDate = payload.marketDate || '';
    TOP_TRADE_TODAY.generatedAt = payload.generatedAt || '';
    TOP_TRADE_TODAY.choppyDayWarning = Boolean(payload.choppyDayWarning);
    TOP_TRADE_TODAY.loading = false;
    TOP_TRADE_TODAY.error = '';
  } catch (error) {
    TOP_TRADE_TODAY.picks = [];
    TOP_TRADE_TODAY.bestOverallPick = '';
    TOP_TRADE_TODAY.namesToAvoid = [];
    TOP_TRADE_TODAY.macroRisks = [];
    TOP_TRADE_TODAY.summary = '';
    TOP_TRADE_TODAY.sessionType = '';
    TOP_TRADE_TODAY.sessionLabel = '';
    TOP_TRADE_TODAY.marketDate = '';
    TOP_TRADE_TODAY.generatedAt = '';
    TOP_TRADE_TODAY.choppyDayWarning = false;
    TOP_TRADE_TODAY.loading = false;
    TOP_TRADE_TODAY.error = 'Run the dashboard server to enable Top Trade Today.';
  }

  renderTopTradeToday();
}

function getTickerDetails(ticker) {
  return DASHBOARD_DATA.tickers.find((item) => item.ticker === ticker)
    || DASHBOARD_DATA.indexes.find((item) => item.ticker === ticker)
    || null;
}

function renderTickerDetailBody(tickerData) {
  const isRankedTicker = Object.prototype.hasOwnProperty.call(tickerData, 'optionsIdea');
  const changeValue = typeof tickerData.friChange === 'number' ? tickerData.friChange : tickerData.change;
  const latestPrice = typeof tickerData.price === 'number' ? tickerData.price : 0;

  return `
    <div class="ticker-detail-topbar">
      <div class="ticker-detail-prices">
        <div class="price-group">
          <span class="price-label">Latest</span>
          <span class="price-value glow-hover">${formatPrice(latestPrice)}</span>
          <span class="price-change ${getChangeClass(changeValue)}">${formatChange(changeValue)}</span>
        </div>
        ${typeof tickerData.ahPrice === 'number' ? `
          <div class="price-group">
            <span class="price-label">After Hours</span>
            <span class="price-value glow-hover" style="font-size:0.95rem;">${formatPrice(tickerData.ahPrice)}</span>
            <span class="price-change ${getChangeClass(tickerData.ahChange)}">${formatChange(tickerData.ahChange)}</span>
          </div>
        ` : ''}
      </div>
      <div class="ticker-detail-badges">
        <span class="badge badge-bias ${getBiasClass(tickerData.bias)}">${escapeHtml(tickerData.bias)}</span>
        <span class="badge badge-strategy">${escapeHtml(tickerData.strategy)}</span>
      </div>
    </div>

    <div class="ticker-detail-grid">
      <div class="ticker-detail-panel">
        <div class="ticker-detail-chart-head">
          <div class="ticker-detail-panel-title">Price Structure</div>
        </div>
        <div class="chart-container ticker-detail-chart">
          <canvas class="ticker-detail-canvas" data-ticker="${tickerData.ticker}"></canvas>
        </div>
        <div class="ticker-triggers">
          <div class="trigger trigger-bull">▲ ${escapeHtml(tickerData.bullTrigger || 'N/A')}</div>
          <div class="trigger trigger-bear">▼ ${escapeHtml(tickerData.bearTrigger || 'N/A')}</div>
        </div>
        <table class="levels-table">
          ${typeof tickerData.prevDayHigh === 'number' ? `
            <tr><td>Prev Day High</td><td>${formatPrice(tickerData.prevDayHigh)}</td></tr>
            <tr><td>Prev Day Low</td><td>${formatPrice(tickerData.prevDayLow)}</td></tr>
            <tr><td>5-Day High</td><td>${formatPrice(tickerData.fiveDayHigh)}</td></tr>
            <tr><td>5-Day Low</td><td>${formatPrice(tickerData.fiveDayLow)}</td></tr>
          ` : ''}
          <tr><td>Support</td><td class="support-vals">${(tickerData.support || []).join(' / ') || '—'}</td></tr>
          <tr><td>Resistance</td><td class="resistance-vals">${(tickerData.resistance || []).join(' / ') || '—'}</td></tr>
        </table>
      </div>

      <div class="ticker-detail-panel">
        <div class="ticker-detail-panel-title">Stats Snapshot</div>
        <div class="ticker-detail-metrics">
          <div class="ticker-detail-metric">
            <span class="ticker-detail-metric-label">RSI (14)</span>
            <span class="ticker-detail-metric-value ${getRsiClass(tickerData.rsi)}">${tickerData.rsi ?? '—'}</span>
          </div>
          <div class="ticker-detail-metric">
            <span class="ticker-detail-metric-label">ATR</span>
            <span class="ticker-detail-metric-value">${tickerData.atr ?? '—'}</span>
          </div>
          <div class="ticker-detail-metric">
            <span class="ticker-detail-metric-label">ATR %</span>
            <span class="ticker-detail-metric-value">${tickerData.atrPct ? `${tickerData.atrPct}%` : '—'}</span>
          </div>
          <div class="ticker-detail-metric">
            <span class="ticker-detail-metric-label">Expected Move</span>
            <span class="ticker-detail-metric-value">${escapeHtml(tickerData.expectedMove || '—')}</span>
          </div>
        </div>
        ${isRankedTicker ? `
          <div class="ticker-meta">
            <div class="meta-row">
              <span class="meta-label">Options</span>
              <span class="meta-value">${escapeHtml(tickerData.optionsIdea)}</span>
            </div>
          </div>
        ` : ''}
        <div class="ticker-detail-summary">${escapeHtml(tickerData.summary || tickerData.strategy || '')}</div>
        <div class="ticker-detail-actions">
          <a class="ticker-detail-link" href="${getTradingViewUrl(tickerData.ticker)}" target="_blank" rel="noopener noreferrer">
            Open in TradingView ↗
          </a>
        </div>
      </div>
    </div>
  `;
}

async function openTickerDetailModal(ticker) {
  const modal   = document.getElementById('tickerDetailModal');
  const title   = document.getElementById('tickerDetailTitle');
  const subtitle = document.getElementById('tickerDetailSubtitle');
  const body    = document.getElementById('tickerDetailBody');

  let tickerData = getTickerDetails(ticker);

  if (!tickerData) {
    // Show loading state immediately while we fetch
    title.textContent    = ticker;
    subtitle.textContent = 'Loading…';
    body.innerHTML       = '<div class="ticker-detail-loading"><span class="ticker-detail-spinner"></span>Fetching market data…</div>';
    modal.classList.add('active');

    try {
      const res = await fetch(`/api/market-data?tickers=${encodeURIComponent(ticker)}&fresh=1`, { cache: 'no-store' });
      if (res.ok) {
        const payload = await res.json();
        if (payload.tickers?.length) {
          const existing = DASHBOARD_DATA.tickers || [];
          payload.tickers.forEach(t => {
            if (!existing.find(e => e.ticker === t.ticker)) existing.push(t);
          });
          DASHBOARD_DATA.tickers = existing;
        }
        if (payload.chartData) Object.assign(CHART_DATA, payload.chartData);
        tickerData = getTickerDetails(ticker);
      }
    } catch (_) {}

    if (!tickerData) {
      subtitle.textContent = 'No data available';
      body.innerHTML = '<div class="ticker-detail-loading" style="color:var(--text-muted)">No market data found for this ticker.</div>';
      return;
    }
  }

  title.textContent    = tickerData.ticker;
  subtitle.textContent = tickerData.name || 'Trading detail';
  body.innerHTML       = renderTickerDetailBody(tickerData);
  modal.classList.add('active');

  requestAnimationFrame(() => {
    const canvas = body.querySelector('.ticker-detail-canvas');
    const data   = CHART_DATA[tickerData.ticker];
    const levels = getLevelsForTicker(tickerData.ticker);
    if (canvas && data) {
      drawCandlestickChart(canvas, data, levels, {
        showRichHeader: true,
        symbol: tickerData.ticker,
      });
    }
  });
}

function closeTickerDetailModal() {
  const modal = document.getElementById('tickerDetailModal');
  const body = document.getElementById('tickerDetailBody');
  modal.classList.remove('active');
  body.innerHTML = '';
}

function handleWatchlistKeydown(event, ticker) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    openTickerDetailModal(ticker);
  }
}

function initCollapsibleSections() {
  document.querySelectorAll('[data-collapsible]').forEach((section) => {
    const toggle = section.querySelector('.section-toggle');
    const bodyId = toggle?.getAttribute('aria-controls');
    const body = bodyId ? document.getElementById(bodyId) : null;
    if (!toggle || !body) return;

    toggle.addEventListener('click', () => {
      const isExpanded = section.classList.contains('is-expanded');
      section.classList.toggle('is-expanded', !isExpanded);
      section.classList.toggle('is-collapsed', isExpanded);
      toggle.setAttribute('aria-expanded', String(!isExpanded));
      body.hidden = isExpanded;

      if (!isExpanded) {
        requestAnimationFrame(() => initAllCharts());
      }
    });
  });
}

// ============================================
// Custom Ticker Management (in-memory)
// ============================================

let customTickersList = [];

// ============================================
// Supabase Auth + Subscription helpers
// ============================================

async function fetchPublicAuthConfig() {
  const response = await fetch('/api/public-config', { cache: 'no-store' });
  if (!response.ok) throw new Error('Auth config unavailable');
  return response.json();
}

/** Initialise the Supabase JS client once we have URL + anon key. */
function initSupabaseClient(url, anonKey) {
  if (_supabase || !url || !anonKey) return;
  _supabase = window.supabase.createClient(url, anonKey);
}

/** Trigger Supabase Google OAuth (redirects → comes back with session hash). */
async function signInWithGoogle() {
  if (!_supabase) return;
  const note = document.getElementById('authGateNote');
  if (note) note.textContent = 'Redirecting to Google…';
  await _supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin + '/' },
  });
}

/** Sign out of Supabase and reset all local state. */
async function signOut() {
  saveTickerList(AUTH_STATE.user, customTickersList);
  if (_supabase) await _supabase.auth.signOut();
  AUTH_STATE.user = null;
  AUTH_STATE.subscription = { checked: false, hasAccess: false, status: 'none', trialEndsAt: null, currentPeriodEndsAt: null };
  saveStoredGoogleUser(null);
  customTickersList = loadSavedTickers(null);
  renderAuthControls();
  renderCustomTickers();
  await Promise.allSettled([fetchOptionsFlow(), fetchMarketData()]);
}

/**
 * Ask the backend whether the current user has an active dashboard subscription.
 * Requires a live Supabase session (access_token used as Bearer).
 */
async function checkSubscriptionStatus() {
  if (!_supabase) return;
  try {
    const { data: { session } } = await _supabase.auth.getSession();
    if (!session) return;

    const resp = await fetch('/api/subscription-status', {
      headers: { 'Authorization': `Bearer ${session.access_token}` },
      cache: 'no-store',
    });
    if (!resp.ok) return;

    const data = await resp.json();
    AUTH_STATE.subscription = {
      checked: true,
      hasAccess: data.hasAccess === true,
      status: data.status || 'none',
      trialEndsAt: data.trialEndsAt || null,
      currentPeriodEndsAt: data.currentPeriodEndsAt || null,
    };
  } catch (_) {
    AUTH_STATE.subscription.checked = true;
  }
  renderAuthControls();
}

/** POST to /api/stripe-checkout and redirect to the Stripe Checkout page. */
async function startDashboardCheckout() {
  if (!_supabase) return;
  const btn = document.getElementById('authGateTrialBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }

  try {
    const { data: { session } } = await _supabase.auth.getSession();
    if (!session) throw new Error('No session');

    const resp = await fetch('/api/stripe-checkout', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${session.access_token}` },
    });
    const data = await resp.json();
    if (data.url) {
      window.location.href = data.url;
    } else {
      throw new Error(data.error || 'Checkout failed');
    }
  } catch (err) {
    const note = document.getElementById('authGateSubscribeNote');
    if (note) note.textContent = 'Could not start checkout. Please try again.';
    if (btn) { btn.disabled = false; btn.textContent = 'Start Free Trial'; }
  }
}

/** POST to /api/stripe-portal and redirect to the Stripe Billing Portal. */
async function openBillingPortal() {
  if (!_supabase) return;
  try {
    const { data: { session } } = await _supabase.auth.getSession();
    if (!session) throw new Error('No session');

    const resp = await fetch('/api/stripe-portal', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${session.access_token}` },
    });
    const data = await resp.json();
    if (data.url) window.location.href = data.url;
  } catch (_) {
    /* silent — portal is a convenience, not a blocker */
  }
}

/**
 * Render the dashboard gate overlay.
 * Three states:
 *   1. No user       → show sign-in card
 *   2. User, no sub  → show subscribe/trial card
 *   3. User, active  → hide overlay, unlock dashboard
 */
function renderAuthGate() {
  const wrap = document.getElementById('dashboardGateWrap');
  const addTickerBtns = [
    document.getElementById('addTickerBtn'),
    document.getElementById('addTickerBtnInline'),
  ].filter(Boolean);
  if (!wrap) return;

  const signInCard = document.getElementById('authGateSignIn');
  const subscribeCard = document.getElementById('authGateSubscribe');
  const subscribeNote = document.getElementById('authGateSubscribeNote');
  const manageBillingBtn = document.getElementById('authGateManageBillingBtn');

  const hasUser = !!AUTH_STATE.user;
  const sub = AUTH_STATE.subscription;
  // Unlock when we have confirmed active/trialing access
  const unlocked = hasUser && sub.checked && sub.hasAccess;

  // Lock/unlock the gated content
  wrap.classList.toggle('is-locked', !unlocked);
  addTickerBtns.forEach((btn) => {
    btn.disabled = !unlocked;
    btn.setAttribute('aria-disabled', unlocked ? 'false' : 'true');
    btn.title = unlocked ? 'Add a custom ticker' : 'Sign in and subscribe to add tickers';
  });

  if (!hasUser) {
    // State 1: signed out
    if (signInCard) signInCard.style.display = '';
    if (subscribeCard) subscribeCard.style.display = 'none';

  } else if (!unlocked) {
    // State 2: signed in but no valid subscription
    if (signInCard) signInCard.style.display = 'none';
    if (subscribeCard) subscribeCard.style.display = '';

    if (subscribeNote && sub.checked) {
      // Show context-appropriate note
      const s = sub.status;
      if (s === 'past_due' || s === 'unpaid') {
        subscribeNote.textContent = 'Your subscription has a payment issue. Update your payment method below.';
        if (manageBillingBtn) manageBillingBtn.style.display = '';
      } else if (s === 'canceled') {
        subscribeNote.textContent = 'Your subscription was canceled. Start a new trial below.';
      } else if (s === 'incomplete' || s === 'incomplete_expired') {
        subscribeNote.textContent = 'Your last checkout was incomplete. Start a new trial below.';
      } else {
        subscribeNote.textContent = '';
      }
    }

  } else {
    // State 3: unlocked — hide the entire overlay
    if (signInCard) signInCard.style.display = 'none';
    if (subscribeCard) subscribeCard.style.display = 'none';
  }
}

function persistTicker() {
  return saveTickerList();
}

function deleteTicker() {
  return saveTickerList();
}

async function initAuth(forceRefresh = false) {
  if (AUTH_STATE.configLoaded && !forceRefresh) {
    renderAuthControls();
    return;
  }

  AUTH_STATE.error = '';
  AUTH_STATE.configLoaded = false;
  renderAuthControls();

  try {
    // 1. Fetch public config (includes Supabase URL + anon key)
    const config = await fetchPublicAuthConfig();
    AUTH_STATE.configLoaded = true;
    AUTH_STATE.googleClientId = config.googleClientId || "";  // legacy display
    APP_CONFIG.tradingViewProductName = config.tradingViewProductName || APP_CONFIG.tradingViewProductName;
    APP_CONFIG.tradingViewProductDescription = config.tradingViewProductDescription || APP_CONFIG.tradingViewProductDescription;
    APP_CONFIG.monthlyPlan = {
      ...APP_CONFIG.monthlyPlan,
      link: config.tradingViewMonthlyLink || "",
      name: config.tradingViewMonthlyName || APP_CONFIG.monthlyPlan.name,
      price: config.tradingViewMonthlyPrice || APP_CONFIG.monthlyPlan.price,
      description: config.tradingViewMonthlyDescription || APP_CONFIG.monthlyPlan.description,
    };
    APP_CONFIG.lifetimePlan = {
      ...APP_CONFIG.lifetimePlan,
      link: config.tradingViewLifetimeLink || config.stripePaymentLink || "",
      name: config.tradingViewLifetimeName || APP_CONFIG.lifetimePlan.name,
      price: config.tradingViewLifetimePrice || config.tradingViewProductPriceLabel || APP_CONFIG.lifetimePlan.price,
      description: config.tradingViewLifetimeDescription || APP_CONFIG.lifetimePlan.description,
    };
    renderProductOffer();

    // 2. Boot Supabase client
    initSupabaseClient(config.supabaseUrl, config.supabaseAnonKey);

    if (!_supabase) {
      // Supabase not configured yet — show gate without crashing
      renderAuthControls();
      return;
    }

    // 3. Listen for auth state changes (handles OAuth redirects + session refresh)
    _supabase.auth.onAuthStateChange(async (event, session) => {
      const previousUser = AUTH_STATE.user;
      if (previousUser) saveTickerList(previousUser, customTickersList);

      AUTH_STATE.user = session?.user ?? null;
      // Reset subscription state on every auth change; re-check if signed in
      AUTH_STATE.subscription = { checked: false, hasAccess: false, status: 'none', trialEndsAt: null, currentPeriodEndsAt: null };

      if (AUTH_STATE.user) {
        syncTickersForCurrentUser();
        renderAuthControls();
        renderCustomTickers();
        // Check subscription in the background; gate stays locked until confirmed
        checkSubscriptionStatus().then(() => {
          if (AUTH_STATE.subscription.hasAccess) {
            Promise.allSettled([fetchOptionsFlow(), fetchMarketData(), fetchTopTradeToday(true)]);
          }
        });
      } else {
        customTickersList = loadSavedTickers(null);
        renderAuthControls();
        renderCustomTickers();
      }
    });

    // 4. Check for an existing session on page load
    const { data: { session } } = await _supabase.auth.getSession();
    if (session?.user) {
      AUTH_STATE.user = session.user;
      syncTickersForCurrentUser();
      await checkSubscriptionStatus();
    }

    renderAuthControls();

    // 5. Show checkout=success banner if returning from Stripe
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('checkout') === 'success') {
      // Remove query param without reloading
      window.history.replaceState({}, '', window.location.pathname);
      // Re-poll subscription status (webhook may still be in-flight)
      setTimeout(() => checkSubscriptionStatus(), 2000);
    }

  } catch (error) {
    AUTH_STATE.configLoaded = true;
    AUTH_STATE.error = 'Auth unavailable';
    renderProductOffer();
    renderAuthControls();
  }
}

function addCustomTicker(symbol) {
  const ticker = symbol.toUpperCase().trim();
  if (!ticker || ticker.length > 5) return false;
  
  if (BUILT_IN_TICKERS.has(ticker)) return 'exists';
  
  // Check if already in custom list
  if (customTickersList.includes(ticker)) return 'duplicate';
  
  customTickersList.push(ticker);
  customTickersList = normalizeTickerList(customTickersList);
  return ticker;
}

async function removeCustomTicker(ticker) {
  customTickersList = customTickersList.filter(t => t !== ticker);
  deleteTicker(ticker);
  renderCustomTickers();
  await Promise.allSettled([fetchOptionsFlow(), fetchMarketData()]);
}

function renderCustomTickers() {
  const grid = document.getElementById('customTickerGrid');
  if (!grid) return;
  const filtered = normalizeTickerList(customTickersList);
  customTickersList = filtered;
  
  if (filtered.length === 0) {
    grid.innerHTML = `<div class="tracked-ticker-empty">No custom tickers yet — use "Add Ticker" in the header to track a symbol across the dashboard.</div>`;
    return;
  }
  
  grid.innerHTML = filtered.map((ticker) => `
    <div class="tracked-ticker-chip">
      <a class="tracked-ticker-chip-symbol" href="${getTradingViewUrl(ticker)}" target="_blank" rel="noopener">${escapeHtml(ticker)}</a>
      <span class="tracked-ticker-chip-note">${AUTH_STATE.user ? 'saved to this signed-in account on this browser' : 'saved on this browser until you sign in'}</span>
      <button class="tracked-ticker-chip-remove" onclick="removeCustomTicker('${escapeHtml(ticker)}')" title="Remove ${escapeHtml(ticker)}">×</button>
    </div>
  `).join('');
}

function getTrackedCustomTickers() {
  return normalizeTickerList(customTickersList);
}

function buildTickerQuery() {
  const extras = getTrackedCustomTickers();
  if (!extras.length) return '';
  return `?tickers=${encodeURIComponent(extras.join(','))}`;
}

// Modal logic
function initAddTickerModal() {
  const modal = document.getElementById('addTickerModal');
  const buttons = [
    document.getElementById('addTickerBtn'),
    document.getElementById('addTickerBtnInline'),
  ].filter(Boolean);
  const input = document.getElementById('tickerInput');
  const addBtn = document.getElementById('modalAdd');
  const cancelBtn = document.getElementById('modalCancel');
  const closeBtn = document.getElementById('modalClose');
  if (!modal || !buttons.length || !input || !addBtn || !cancelBtn || !closeBtn) return;
  
  function openModal() {
    modal.classList.add('active');
    input.value = '';
    input.focus();
  }
  
  function closeModal() {
    modal.classList.remove('active');
    input.value = '';
  }
  
  async function handleAdd() {
    const val = input.value.trim();
    if (!val) return;
    
    const result = addCustomTicker(val);
    if (result === 'exists') {
      input.style.borderColor = 'var(--amber)';
      input.setAttribute('placeholder', 'Already on dashboard');
      input.value = '';
      setTimeout(() => {
        input.style.borderColor = '';
        input.setAttribute('placeholder', 'e.g. NFLX, SMCI, COIN');
      }, 1500);
      return;
    }
    if (result === 'duplicate') {
      input.style.borderColor = 'var(--amber)';
      input.setAttribute('placeholder', 'Already added');
      input.value = '';
      setTimeout(() => {
        input.style.borderColor = '';
        input.setAttribute('placeholder', 'e.g. NFLX, SMCI, COIN');
      }, 1500);
      return;
    }

    const saved = persistTicker(result);
    if (!saved) {
      customTickersList = customTickersList.filter((ticker) => ticker !== result);
    }

    closeModal();
    renderCustomTickers();
    await Promise.allSettled([fetchOptionsFlow(), fetchMarketData()]);
  }
  
  buttons.forEach((button) => button.addEventListener('click', openModal));
  cancelBtn.addEventListener('click', closeModal);
  closeBtn.addEventListener('click', closeModal);
  addBtn.addEventListener('click', handleAdd);
  
  // Enter key to add
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleAdd();
    if (e.key === 'Escape') closeModal();
  });
  
  // Click outside to close
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });
}

function initAlertCenter() {
  loadTradeAlerts();
  renderAlertsPill();
  renderAlertBar();
  document.getElementById('alertsTogglePill')?.addEventListener('click', enableBrowserAlerts);
}

function initTickerDetailModal() {
  const modal = document.getElementById('tickerDetailModal');
  const closeBtn = document.getElementById('tickerDetailClose');

  closeBtn.addEventListener('click', closeTickerDetailModal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeTickerDetailModal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeTickerDetailModal();
    }
  });
}

// ============================================
// Ticker Hover Popup
// ============================================

let _thpHideTimer = null;
let _thpShowTimer = null;

function positionHoverPopup(popup, anchorEl) {
  const pad = 12;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const rect = anchorEl.getBoundingClientRect();
  const pw = popup.offsetWidth || 400;
  const ph = popup.offsetHeight || 320;

  // Prefer right of anchor, fall back to left
  let left = rect.right + pad;
  if (left + pw > vw - pad) left = rect.left - pw - pad;
  left = Math.max(pad, Math.min(left, vw - pw - pad));

  // Vertically center on anchor, clamp to viewport
  let top = rect.top + rect.height / 2 - ph / 2;
  top = Math.max(pad, Math.min(top, vh - ph - pad));

  popup.style.left = `${left}px`;
  popup.style.top  = `${top}px`;
}

function showTickerHoverPopup(ticker, anchorEl) {
  clearTimeout(_thpHideTimer);
  const popup    = document.getElementById('tickerHoverPopup');
  const tickerData = getTickerDetails(ticker);
  if (!tickerData) return;

  const changeVal = tickerData.friChange ?? tickerData.change;
  const isPos = typeof changeVal === 'number' && changeVal >= 0;
  const changeColor = isPos ? '#34d399' : '#f87171';
  const changeSign  = isPos ? '+' : '';

  document.getElementById('thpSymbol').textContent  = tickerData.ticker;
  document.getElementById('thpName').textContent    = tickerData.name || '';
  document.getElementById('thpPrice').textContent   = typeof tickerData.price === 'number' ? `$${tickerData.price.toFixed(2)}` : '—';
  const chEl = document.getElementById('thpChange');
  chEl.textContent  = typeof changeVal === 'number' ? `${changeSign}${changeVal.toFixed(2)}%` : '';
  chEl.style.color  = changeColor;

  const rsiEl = document.getElementById('thpRsi');
  rsiEl.textContent = tickerData.rsi ?? '—';
  rsiEl.className   = `thp-stat-val ${getRsiClass(tickerData.rsi)}`;

  document.getElementById('thpAtrPct').textContent  = tickerData.atrPct ? `${tickerData.atrPct}%` : '—';
  document.getElementById('thpMove').textContent    = tickerData.expectedMove || '—';
  const biasEl = document.getElementById('thpBias');
  biasEl.textContent = tickerData.bias || '—';
  biasEl.style.color = tickerData.bias?.toLowerCase().includes('bull') ? '#34d399' : '#f87171';

  document.getElementById('thpBull').textContent = `▲ ${tickerData.bullTrigger || '—'}`;
  document.getElementById('thpBear').textContent = `▼ ${tickerData.bearTrigger || '—'}`;

  // Position before showing so offsetHeight is correct
  popup.style.opacity    = '0';
  popup.style.visibility = 'visible';
  positionHoverPopup(popup, anchorEl);
  popup.classList.add('thp-visible');

  // Draw chart
  const canvas = document.getElementById('thpCanvas');
  const data   = CHART_DATA[ticker];
  const levels = getLevelsForTicker(ticker);
  if (canvas && data) {
    requestAnimationFrame(() => drawCandlestickChart(canvas, data, levels));
  }
}

function hideTickerHoverPopup(delay = 120) {
  clearTimeout(_thpShowTimer);
  _thpHideTimer = setTimeout(() => {
    const popup = document.getElementById('tickerHoverPopup');
    popup.classList.remove('thp-visible');
  }, delay);
}

function initTickerHoverPopup() {
  const popup = document.getElementById('tickerHoverPopup');
  popup.addEventListener('mouseenter', () => clearTimeout(_thpHideTimer));
  popup.addEventListener('mouseleave', () => hideTickerHoverPopup());

  // Delegate hover on any [data-hover-ticker] element
  document.addEventListener('mouseenter', (e) => {
    const el = e.target.closest('[data-hover-ticker]');
    if (!el) return;
    clearTimeout(_thpHideTimer);
    _thpShowTimer = setTimeout(() => showTickerHoverPopup(el.dataset.hoverTicker, el), 180);
  }, true);

  document.addEventListener('mouseleave', (e) => {
    if (!e.target.closest('[data-hover-ticker]')) return;
    hideTickerHoverPopup();
  }, true);
}

// ============================================
// Live Market Data
// ============================================

async function fetchMarketData(forceFresh = false) {
  try {
    const query = buildTickerQuery();
    const separator = query ? '&' : '?';
    const source = forceFresh
      ? `/api/market-data${query}${separator}fresh=1&t=${Date.now()}`
      : `/api/market-data${query}`;
    const response = await fetch(source, { cache: 'no-store' });
    if (!response.ok) return;

    const payload = await response.json();
    if (!payload.liveData || payload.error) return;

    // Replace static dashboard data with live computed data
    if (payload.tickers && payload.tickers.length > 0) {
      DASHBOARD_DATA.tickers = payload.tickers;
    }
    if (payload.indexes && payload.indexes.length > 0) {
      DASHBOARD_DATA.indexes = payload.indexes;
    }
    if (payload.watchlist && payload.watchlist.length > 0) {
      DASHBOARD_DATA.watchlist = payload.watchlist;
    }

    // Replace static OHLCV chart data with live bars
    if (payload.chartData && typeof payload.chartData === 'object') {
      Object.assign(CHART_DATA, payload.chartData);
    }

    // Update date label to reflect live data timestamp
    if (payload.updatedAt) {
      const updatedDate = new Date(payload.updatedAt * 1000);
      DASHBOARD_DATA.date = updatedDate.toLocaleDateString('en-US', {
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
      });
      DASHBOARD_DATA.lastUpdatedTime = updatedDate.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit'
      });
    }

    // Re-render all data-driven sections
    renderHeader();
    renderIndexCards();
    renderTickerCards();
    renderWatchlist();
    renderMarketRadar();
    renderCustomTickers();
    evaluateTradeAlerts();

    // Update footer disclaimer
    const footer = document.querySelector('.footer-disclaimer');
    if (footer && payload.updatedAt) {
      const t = new Date(payload.updatedAt * 1000);
      footer.textContent = `Live data as of ${t.toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric'
      })} ${t.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}. `
        + 'Indicators computed from Yahoo Finance daily bars. Not financial advice.';
    }

    // Render ticker tape
    renderTickerTape(payload.tickers, payload.indexes, payload.vix);

    // Render VIX badge and Market Pulse
    if (payload.vix) {
      renderVixBadge(payload.vix);
    }
    if (payload.marketBreadth) {
      renderMarketPulse(payload.marketBreadth);
    }

    // Render backtest accuracy tables
    if (payload.backtestStats) {
      renderBacktest(payload.backtestStats, payload.backtestN || 0);
    }
    if (payload.backtestPerTicker) {
      renderBacktestPerTicker(payload.backtestPerTicker);
    }

    // Redraw sparkline charts with live OHLCV
    requestAnimationFrame(() => initAllCharts());

  } catch (err) {
    // Silent fail — static dashboard data remains visible
    console.warn('[Option Riders] Live market data unavailable:', err.message);
  }
}

// ============================================
// Ticker Tape
// ============================================

function renderTickerTape(tickers, indexes, vix) {
  const track = document.getElementById('ticker-tape');
  if (!track) return;

  const items = [];
  const formatTapePrice = (value, ticker) => {
    if (!Number.isFinite(value)) return '';
    if (ticker === 'ES' || ticker === 'NQ') return String(Math.round(value));
    if (ticker === 'VIX') return value.toFixed(2);
    return value >= 100 ? value.toFixed(2) : value.toFixed(2);
  };

  // Indexes first (SPY, QQQ, ES, NQ)
  (indexes || []).forEach(idx => {
    const pct = idx.friChange ?? idx.change;
    if (pct == null) return;
    items.push({ t: idx.ticker, pct, price: idx.price });
  });

  // Main tickers
  (tickers || []).forEach(t => {
    const pct = t.friChange ?? t.change;
    if (pct == null) return;
    items.push({ t: t.ticker, pct, price: t.price });
  });

  // VIX
  if (vix && vix.changePct != null) {
    items.push({ t: 'VIX', pct: vix.changePct, price: vix.price });
  }

  if (!items.length) return;

  // Duplicate for seamless loop
  const all = [...items, ...items];
  track.innerHTML = all.map(({ t, pct, price }) => {
    const pos = pct >= 0;
    const sign = pos ? '+' : '';
    const color = pos ? '#34d399' : '#f87171';
    const priceText = formatTapePrice(price, t);
    return `<span style="margin:0 28px;font-size:12px;font-weight:500;white-space:nowrap;color:${color};font-family:'JetBrains Mono',monospace;">${t}${priceText ? ` ${priceText}` : ''}&nbsp;&nbsp;${sign}${pct.toFixed(2)}%</span>`;
  }).join('');
}

// ============================================
// Backtest Rendering
// ============================================

const BACKTEST_BUCKET_ORDER = ['STRONG BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG SELL'];

function renderBacktest(stats, totalN) {
  const tbody = document.getElementById('backtestBody');
  const meta  = document.getElementById('backtestMeta');
  const note  = document.getElementById('backtestNote');
  if (!tbody) return;

  if (!stats || Object.keys(stats).length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="color:var(--text-muted);text-align:center;">No backtest data — live market data required.</td></tr>`;
    return;
  }

  if (meta) meta.textContent = `Walk-forward backtest · ${totalN} signal observations · 90-day window · no lookahead bias`;

  function winCell(pct) {
    if (pct == null) return '<span style="color:var(--text-muted)">—</span>';
    const cls = pct >= 60 ? 'bt-strong' : pct >= 52 ? 'bt-ok' : pct < 45 ? 'bt-weak' : 'bt-flat';
    return `<span class="${cls}">${pct}%</span>`;
  }

  function retCell(avg) {
    if (avg == null) return '<span style="color:var(--text-muted)">—</span>';
    const sign = avg >= 0 ? '+' : '';
    const cls  = avg >= 0.3 ? 'bt-strong' : avg <= -0.3 ? 'bt-weak' : 'bt-flat';
    return `<span class="${cls}">${sign}${avg}%</span>`;
  }

  const scoreForBucket = { 'STRONG BUY': 75, 'BUY': 30, 'NEUTRAL': 0, 'SELL': -30, 'STRONG SELL': -75 };

  tbody.innerHTML = BACKTEST_BUCKET_ORDER.map(name => {
    const row = stats[name];
    const badge = renderSignalBadge(scoreForBucket[name]);
    if (!row || row.n === 0) return `
      <tr>
        <td>${badge}</td>
        <td style="color:var(--text-muted)">—</td>
        <td colspan="6" style="color:var(--text-muted)">No observations</td>
      </tr>`;
    return `
      <tr>
        <td>${badge}</td>
        <td style="color:var(--text-muted);font-weight:600">${row.n}</td>
        <td>${winCell(row.win1d)}</td>
        <td>${retCell(row.avg1d)}</td>
        <td>${winCell(row.win3d)}</td>
        <td>${retCell(row.avg3d)}</td>
        <td>${winCell(row.win5d)}</td>
        <td>${retCell(row.avg5d)}</td>
      </tr>`;
  }).join('');

  if (note) note.textContent = 'Win% = % of signals where price closed higher after N days. Avg Ret = mean % return. Computed from Yahoo Finance daily closes. Past performance does not predict future results.';
}

function renderBacktestPerTicker(perTicker) {
  const container = document.getElementById('backtestPerTickerWrap');
  if (!container || !perTicker || Object.keys(perTicker).length === 0) return;

  const scoreForBucket = { 'STRONG BUY': 75, 'BUY': 30, 'NEUTRAL': 0, 'SELL': -30, 'STRONG SELL': -75 };

  function mini(pct) {
    if (pct == null) return '<span style="color:var(--text-muted)">—</span>';
    const cls = pct >= 60 ? 'bt-strong' : pct >= 52 ? 'bt-ok' : pct < 45 ? 'bt-weak' : 'bt-flat';
    return `<span class="${cls}">${pct}%</span>`;
  }

  const rows = Object.entries(perTicker).map(([ticker, stats]) => {
    const buy  = stats['STRONG BUY']  || stats['BUY']  || {};
    const sell = stats['STRONG SELL'] || stats['SELL'] || {};
    return `<tr>
      <td style="color:var(--text-bright);font-weight:700">${escapeHtml(ticker)}</td>
      <td>${mini(buy.win1d)}</td><td>${mini(buy.win5d)}</td>
      <td>${mini(sell.win1d)}</td><td>${mini(sell.win5d)}</td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <div class="options-flow-panel-title" style="margin-top:18px">Per-Ticker Signal Accuracy</div>
    <div class="table-wrapper">
      <table class="data-table backtest-table">
        <thead><tr>
          <th>Ticker</th>
          <th>Buy 1D</th><th>Buy 5D</th>
          <th>Sell 1D</th><th>Sell 5D</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="backtest-note">Best Buy/Sell bucket shown per ticker. Win% = price higher after N days.</p>`;
}

// ============================================
// Signal Merging — combine options flow sentiment with technical scores
// ============================================

function mergeOptionsFlowIntoScores() {
  // Build a sentiment map from unusual options: ticker → net boost (-15 to +15)
  const sentimentMap = {};
  for (const row of OPTIONS_FLOW.unusual) {
    const sym = row.baseSymbol;
    if (!sym) continue;
    const s = (row.sentiment || '').toLowerCase();
    const boost = s.includes('bullish') ? 15 : s.includes('bearish') ? -15 : 0;
    if (boost !== 0) {
      sentimentMap[sym] = (sentimentMap[sym] || 0) + boost;
    }
  }

  if (Object.keys(sentimentMap).length === 0) return; // nothing to merge

  let changed = false;

  // Apply boost to tickers
  for (const t of DASHBOARD_DATA.tickers) {
    if (t.signalScore == null) continue;
    const boost = sentimentMap[t.ticker] || 0;
    if (boost !== 0) {
      t.signalScore = Math.max(-100, Math.min(100, t.signalScore + boost));
      changed = true;
    }
  }

  // Apply boost to watchlist
  for (const w of DASHBOARD_DATA.watchlist) {
    if (w.signalScore == null) continue;
    const boost = sentimentMap[w.ticker] || 0;
    if (boost !== 0) {
      w.signalScore = Math.max(-100, Math.min(100, w.signalScore + boost));
      changed = true;
    }
  }

  if (changed) {
    renderTickerCards();
    renderWatchlist();
    renderMarketRadar();
  }
}

// ============================================
// Initialize
// ============================================

// ============================================
// Auto-Refresh (every 5 minutes while page is open)
// ============================================

const AUTO_REFRESH_MS = 5 * 60 * 1000;  // 5 minutes
let _refreshCountdown = AUTO_REFRESH_MS / 1000;
let _refreshTimer     = null;
let _countdownTimer   = null;

function _updateRefreshBadge() {
  const badge = document.getElementById('refreshCountdown');
  if (!badge) return;
  const mins = Math.floor(_refreshCountdown / 60);
  const secs = String(_refreshCountdown % 60).padStart(2, '0');
  badge.textContent = `Refresh in ${mins}:${secs}`;
}

async function _autoRefresh() {
  _refreshCountdown = AUTO_REFRESH_MS / 1000;
  const badge = document.getElementById('refreshCountdown');
  if (badge) badge.textContent = 'Refreshing…';

  await Promise.allSettled([fetchOptionsFlow(true), fetchMarketData(true), fetchTopWatch(true), fetchTopTradeToday(true)]);
  mergeOptionsFlowIntoScores();
  requestAnimationFrame(() => initAllCharts());
}

function initAutoRefresh() {
  // Inject countdown badge next to market status
  const headerRight = document.querySelector('.header-right');
  if (headerRight) {
    const badge = document.createElement('span');
    badge.id        = 'refreshCountdown';
    badge.className = 'badge badge-market';
    badge.style.cssText = 'font-size:0.62rem;opacity:0.7;cursor:default;';
    badge.title     = 'Auto-refreshes market data every 5 minutes';
    headerRight.prepend(badge);
    _updateRefreshBadge();
  }

  _countdownTimer = setInterval(() => {
    _refreshCountdown = Math.max(0, _refreshCountdown - 1);
    _updateRefreshBadge();
  }, 1000);

  _refreshTimer = setInterval(_autoRefresh, AUTO_REFRESH_MS);
}

// ============================================
// Initialize
// ============================================

async function init() {
  await initAuth();
  initAlertCenter();
  renderProductOffer();
  renderHeader();
  renderAuthControls();
  renderAlertBar();
  renderCatalysts();
  renderCalendar();
  renderMarketRadar();
  renderTopTradeToday();
  renderIndexCards();
  renderTickerCards();
  renderTopWatch();
  renderWatchlist();
  renderThemes();
  renderCustomTickers();
  renderTickerTape(DASHBOARD_DATA.tickers, DASHBOARD_DATA.indexes, null);
  renderOptionsFlow();
  initCollapsibleSections();
  initAddTickerModal();
  initTickerDetailModal();
  initTickerHoverPopup();
  fetchAppVersion();
  await Promise.allSettled([
    fetchEconomicCalendar(),
    fetchOptionsFlow(),
    fetchMarketData(),
    fetchTopWatch(),
    fetchTopTradeToday(true),
  ]);
  // Merge options flow sentiment into signal scores now that both fetches are done
  mergeOptionsFlowIntoScores();
  // Draw sparkline charts after DOM is ready (live data already merged above if available)
  requestAnimationFrame(() => initAllCharts());
  // Start auto-refresh cycle
  initAutoRefresh();
}

// Run on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
