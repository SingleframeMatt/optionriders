/* ============================================
   Option Riders — Application Logic
   ============================================ */

const DASHBOARD_DATA = {
  date: "Monday, March 16, 2026",
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
  
  tickers: [
    {
      rank: 1, ticker: "NVDA", name: "NVIDIA", price: 180.25, friChange: -1.59,
      ahPrice: 180.20, ahChange: -0.03, bias: "Neutral → Bullish", star: true,
      rsi: 45.2, atr: 5.71, atrPct: 3.17,
      prevDayHigh: 186.09, prevDayLow: 179.94,
      fiveDayHigh: 187.62, fiveDayLow: 175.56,
      support: [179, 176, 174], resistance: [184, 187, 192],
      bullTrigger: "Break above 184 post-keynote", bearTrigger: "Lose 179",
      strategy: "Momentum Breakout", 
      optionsIdea: "ATM calls or 185c for GTC pop; put spreads below 178",
      expectedMove: "±$5-7 (3-4%)",
      summary: "NVDA is THE trade of the day. Jensen Huang keynote is a binary event. Long above 184 targeting 190+."
    },
    {
      rank: 2, ticker: "MU", name: "Micron", price: 426.13, friChange: 5.13,
      ahPrice: 425.00, ahChange: -0.27, bias: "Bullish", star: true,
      rsi: 57.1, atr: 26.47, atrPct: 6.21,
      prevDayHigh: 429.35, prevDayLow: 413.00,
      fiveDayHigh: 429.35, fiveDayLow: 357.67,
      support: [413, 405, 397], resistance: [429, 437, 445],
      bullTrigger: "Break above 429.35", bearTrigger: "Lose 413",
      strategy: "Momentum Continuation",
      optionsIdea: "Calls above 430 for breakout; call spreads 430/450",
      expectedMove: "±$25-27 (6%)",
      summary: "MU is the strongest large-cap semi — #1 rated with 232% EPS growth projected. Continuation above 430 targets 445."
    },
    {
      rank: 3, ticker: "META", name: "Meta Platforms", price: 613.71, friChange: -3.83,
      ahPrice: 610.90, ahChange: -0.46, bias: "Bearish",
      rsi: 35.8, atr: 19.94, atrPct: 3.25,
      prevDayHigh: 629.17, prevDayLow: 609.55,
      fiveDayHigh: 660.30, fiveDayLow: 609.55,
      support: [609, 600, 590], resistance: [626, 638, 648],
      bullTrigger: "Reclaim 626", bearTrigger: "Lose 609",
      strategy: "Breakdown Short",
      optionsIdea: "Puts below 609 targeting 595; contrarian call spreads above 625",
      expectedMove: "±$18-20 (3%)",
      summary: "META dumped -3.8% on heavy volume into oversold RSI. Watch 609 — lose it and 600 is next."
    },
    {
      rank: 4, ticker: "AVGO", name: "Broadcom", price: 322.16, friChange: -4.11,
      ahPrice: 321.08, ahChange: -0.34, bias: "Bearish → Neutral",
      rsi: 44.2, atr: 14.09, atrPct: 4.37,
      prevDayHigh: 338.32, prevDayLow: 321.43,
      fiveDayHigh: 353.14, fiveDayLow: 321.43,
      support: [321, 314, 307], resistance: [332, 338, 345],
      bullTrigger: "Reclaim 330", bearTrigger: "Lose 321",
      strategy: "GTC Sympathy Long",
      optionsIdea: "Calls above 330 for GTC sympathy; puts below 320",
      expectedMove: "±$13-15 (4%)",
      summary: "AVGO down 17% from highs — could rally on NVIDIA GTC sympathy above 330 targeting 345."
    },
    {
      rank: 5, ticker: "AMD", name: "AMD", price: 193.39, friChange: -2.20,
      ahPrice: 192.88, ahChange: -0.26, bias: "Bearish → Neutral",
      rsi: 41.8, atr: 9.10, atrPct: 4.70,
      prevDayHigh: 199.68, prevDayLow: 192.27,
      fiveDayHigh: 209.21, fiveDayLow: 189.02,
      support: [192, 189, 185], resistance: [198, 203, 209],
      bullTrigger: "Reclaim 198", bearTrigger: "Lose 192",
      strategy: "GTC Sympathy",
      optionsIdea: "Calls above 198; puts below 190",
      expectedMove: "±$9-10 (4.5%)",
      summary: "AMD tracking semis lower — GTC catalyst could lift above 198 for a move to 205; below 192 targets 185."
    },
    {
      rank: 6, ticker: "AAPL", name: "Apple", price: 250.12, friChange: -2.21,
      ahPrice: 249.82, ahChange: -0.12, bias: "Bearish",
      rsi: 34.4, atr: 5.67, atrPct: 2.27,
      prevDayHigh: 256.33, prevDayLow: 249.52,
      fiveDayHigh: 262.48, fiveDayLow: 249.52,
      support: [249, 245, 240], resistance: [255, 260, 264],
      bullTrigger: "Reclaim 255", bearTrigger: "Lose 249",
      strategy: "Oversold Bounce",
      optionsIdea: "Put spreads 248/242; contrarian calls above 255",
      expectedMove: "±$5-6 (2.2%)",
      summary: "AAPL deeply oversold with RSI 34 after 8 straight red days. Watch 249 for bounce or breakdown."
    },
    {
      rank: 7, ticker: "TSLA", name: "Tesla", price: 391.20, friChange: -0.96,
      ahPrice: 389.80, ahChange: -0.36, bias: "Bearish",
      rsi: 40.1, atr: 13.98, atrPct: 3.57,
      prevDayHigh: 400.20, prevDayLow: 389.95,
      fiveDayHigh: 416.38, fiveDayLow: 381.40,
      support: [389, 381, 375], resistance: [400, 407, 416],
      bullTrigger: "Reclaim 400", bearTrigger: "Lose 389",
      strategy: "Breakdown Short",
      optionsIdea: "Puts below 388; call spreads above 402",
      expectedMove: "±$13-14 (3.5%)",
      summary: "TSLA after-hours pressing 389 support — lose it and 381 is target. Need 400 reclaim for any bullish case."
    },
    {
      rank: 8, ticker: "MSFT", name: "Microsoft", price: 395.55, friChange: -1.57,
      ahPrice: 395.10, ahChange: -0.11, bias: "Bearish",
      rsi: 41.0, atr: 8.34, atrPct: 2.11,
      prevDayHigh: 404.80, prevDayLow: 394.25,
      fiveDayHigh: 410.21, fiveDayLow: 394.25,
      support: [394, 390, 385], resistance: [401, 405, 410],
      bullTrigger: "Reclaim 401", bearTrigger: "Lose 394",
      strategy: "Breakdown Short",
      optionsIdea: "Put spreads 393/385; calls above 402",
      expectedMove: "±$8-9 (2%)",
      summary: "MSFT broke multi-week range support at 401 — now resistance. Below 394 opens gap to 385."
    },
    {
      rank: 9, ticker: "GOOGL", name: "Alphabet", price: 302.28, friChange: -0.42,
      ahPrice: 301.74, ahChange: -0.18, bias: "Range",
      rsi: 43.0, atr: 7.33, atrPct: 2.43,
      prevDayHigh: 307.69, prevDayLow: 300.44,
      fiveDayHigh: 311.42, fiveDayLow: 294.08,
      support: [300, 296, 294], resistance: [307, 311, 313],
      bullTrigger: "Reclaim 307", bearTrigger: "Lose 300",
      strategy: "Range Fade",
      optionsIdea: "Iron condor 295/300/307/312",
      expectedMove: "±$7 (2.4%)",
      summary: "GOOGL choppy in 294-311 range. Below 300 targets 294; above 307 targets 311."
    },
    {
      rank: 10, ticker: "AMZN", name: "Amazon", price: 207.67, friChange: -0.89,
      ahPrice: 207.30, ahChange: -0.18, bias: "Bearish",
      rsi: 42.0, atr: 5.78, atrPct: 2.78,
      prevDayHigh: 210.56, prevDayLow: 206.22,
      fiveDayHigh: 217.00, fiveDayLow: 206.22,
      support: [206, 203, 200], resistance: [210, 213, 217],
      bullTrigger: "Reclaim 210", bearTrigger: "Lose 206",
      strategy: "Breakdown Short",
      optionsIdea: "Put spreads below 205; calls above 211",
      expectedMove: "±$5-6 (2.8%)",
      summary: "AMZN fading steadily — 206 is the line. Lose it and 200 psychological level is in play."
    }
  ],
  
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
  loading: true,
  error: "",
  updatedAt: ""
};

const AUTH_STATE = {
  configLoaded: false,
  user: null,
  googleClientId: "",
  error: "",
  buttonRendered: false,
};

const GUEST_TICKERS_STORAGE_KEY = 'optionriders-guest-tickers-v1';
const GOOGLE_USER_STORAGE_KEY = 'optionriders-google-user-v1';

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

function loadGuestTickers() {
  try {
    const saved = window.localStorage.getItem(GUEST_TICKERS_STORAGE_KEY);
    const parsed = saved ? JSON.parse(saved) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    return [];
  }
}

function saveGuestTickers() {
  try {
    window.localStorage.setItem(GUEST_TICKERS_STORAGE_KEY, JSON.stringify(customTickersList));
  } catch (error) {
    // Ignore storage failures and keep the in-memory session usable.
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

function getDisplayName(user) {
  if (!user) return '';
  return user.name
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
    'NFLX': 'NASDAQ:NFLX', 'SMCI': 'NASDAQ:SMCI'
  };
  const sym = symbolMap[ticker] || ticker;
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
}

// Draw a candlestick chart with support/resistance levels
function drawCandlestickChart(canvas, ohlcvData, levels) {
  if (!canvas || !ohlcvData || ohlcvData.length < 2) return;
  
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  
  const w = rect.width;
  const h = rect.height;
  const pad = { top: 6, right: 44, bottom: 6, left: 4 };
  
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;
  
  // Find price range across all candles
  let candlePrices = [];
  ohlcvData.forEach(c => { candlePrices.push(c[1], c[2]); }); // highs & lows
  const candleMin = Math.min(...candlePrices);
  const candleMax = Math.max(...candlePrices);
  const candleRange = candleMax - candleMin || 1;
  
  // Filter levels to only those within reasonable range of candle data
  // (handles ES/NQ where levels are in futures pts but chart data is ETF proxy)
  let filteredLevels = null;
  if (levels) {
    const margin = candleRange * 0.5;
    const validSupport = (levels.support || []).filter(s => s >= candleMin - margin && s <= candleMax + margin);
    const validResistance = (levels.resistance || []).filter(r => r >= candleMin - margin && r <= candleMax + margin);
    if (validSupport.length > 0 || validResistance.length > 0) {
      filteredLevels = { support: validSupport, resistance: validResistance };
    }
  }
  
  // Include valid levels in price range calculation
  let allPrices = [...candlePrices];
  if (filteredLevels) {
    filteredLevels.support.forEach(s => allPrices.push(s));
    filteredLevels.resistance.forEach(r => allPrices.push(r));
  }
  const dataMin = Math.min(...allPrices);
  const dataMax = Math.max(...allPrices);
  const priceRange = dataMax - dataMin || 1;
  // Add 5% padding
  const pMin = dataMin - priceRange * 0.05;
  const pMax = dataMax + priceRange * 0.05;
  const pRange = pMax - pMin;
  
  function priceToY(price) {
    return pad.top + chartH - ((price - pMin) / pRange) * chartH;
  }
  
  const n = ohlcvData.length;
  const slotW = chartW / n;
  const candleW = Math.max(2, slotW * 0.55);
  const wickW = Math.max(1, dpr > 1 ? 1.5 : 1);
  
  // --- Draw support/resistance level lines FIRST (behind candles) ---
  if (filteredLevels) {
    ctx.save();
    ctx.setLineDash([4, 3]);
    ctx.lineWidth = 1;
    ctx.font = `${Math.max(9, Math.min(10, h * 0.08))}px JetBrains Mono, monospace`;
    ctx.textBaseline = 'middle';
    
    // Support levels (green)
    (filteredLevels.support || []).forEach(s => {
      const y = priceToY(s);
      if (y >= pad.top && y <= h - pad.bottom) {
        ctx.strokeStyle = 'rgba(0, 255, 136, 0.35)';
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(pad.left + chartW, y);
        ctx.stroke();
        // Label
        ctx.fillStyle = 'rgba(0, 255, 136, 0.7)';
        ctx.textAlign = 'left';
        ctx.fillText(s.toLocaleString(), pad.left + chartW + 3, y);
      }
    });
    
    // Resistance levels (red)
    (filteredLevels.resistance || []).forEach(r => {
      const y = priceToY(r);
      if (y >= pad.top && y <= h - pad.bottom) {
        ctx.strokeStyle = 'rgba(255, 68, 68, 0.35)';
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(pad.left + chartW, y);
        ctx.stroke();
        // Label
        ctx.fillStyle = 'rgba(255, 68, 68, 0.7)';
        ctx.textAlign = 'left';
        ctx.fillText(r.toLocaleString(), pad.left + chartW + 3, y);
      }
    });
    
    ctx.restore();
  }
  
  // --- Draw candlesticks ---
  ohlcvData.forEach((candle, i) => {
    const [open, high, low, close] = candle;
    const x = pad.left + slotW * i + slotW / 2;
    const bullish = close >= open;
    
    const bodyColor = bullish ? '#00ff88' : '#ff4444';
    const wickColor = bullish ? 'rgba(0, 255, 136, 0.6)' : 'rgba(255, 68, 68, 0.6)';
    
    const yHigh = priceToY(high);
    const yLow = priceToY(low);
    const yOpen = priceToY(open);
    const yClose = priceToY(close);
    
    // Draw wick (high-low line)
    ctx.strokeStyle = wickColor;
    ctx.lineWidth = wickW;
    ctx.beginPath();
    ctx.moveTo(x, yHigh);
    ctx.lineTo(x, yLow);
    ctx.stroke();
    
    // Draw body
    const bodyTop = Math.min(yOpen, yClose);
    const bodyHeight = Math.max(Math.abs(yOpen - yClose), 1);
    
    ctx.fillStyle = bodyColor;
    if (bullish) {
      ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyHeight);
    } else {
      // Bearish: filled body
      ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyHeight);
    }
  });
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
  document.getElementById('headerDate').textContent = DASHBOARD_DATA.date;
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

  if (!AUTH_STATE.googleClientId) {
    controls.innerHTML = `<span class="auth-status-pill warning">Add GOOGLE_CLIENT_ID</span>`;
    return;
  }

  if (!AUTH_STATE.user) {
    controls.innerHTML = `
      <span class="auth-status-pill warning">Guest mode</span>
      <div id="googleSignInMount"></div>
    `;
    renderGoogleButton();
    return;
  }

  controls.innerHTML = `
    <span class="auth-status-pill signed-in">${escapeHtml(getDisplayName(AUTH_STATE.user))}</span>
    <button class="auth-action-btn" type="button" onclick="signOut()">Sign out</button>
  `;
}

function renderCatalysts() {
  const strip = document.getElementById('catalystStrip');
  strip.innerHTML = DASHBOARD_DATA.catalysts.map(c => 
    `<span class="catalyst-pill">${escapeHtml(c)}</span>`
  ).join('');
}

function getAlertItems() {
  const alerts = [];
  const todayKey = new Intl.DateTimeFormat('en-CA', {
    timeZone: ECONOMIC_CALENDAR.timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date());

  const todaysEvents = ECONOMIC_CALENDAR.events
    .filter((event) => event.dayKey === todayKey)
    .slice(0, 2)
    .map((event) => ({
      type: 'today',
      text: `Today ${event.timeLabel}: ${event.title}`
    }));

  const upcomingEvent = ECONOMIC_CALENDAR.events
    .find((event) => event.dayKey !== todayKey);

  if (todaysEvents.length) {
    alerts.push(...todaysEvents);
  } else if (upcomingEvent) {
    alerts.push({
      type: 'week',
      text: `Next red-folder event ${upcomingEvent.dayLabelShort} ${upcomingEvent.timeLabel}: ${upcomingEvent.title}`
    });
  }

  DASHBOARD_DATA.catalysts.slice(0, 2).forEach((item, index) => {
    alerts.push({
      type: index === 0 ? 'macro' : 'week',
      text: item
    });
  });

  if (!alerts.length) {
    alerts.push({
      type: 'week',
      text: 'Monitor Fed headlines, opening drive volatility, and watchlist liquidity before entries.'
    });
  }

  return alerts.slice(0, 4);
}

function renderAlertBar() {
  const track = document.getElementById('alertBarTrack');
  if (!track) return;

  track.innerHTML = getAlertItems().map((alert) => `
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
      meta.textContent = `USD red folder only · Loading weekly events...`;
    }
  }

  if (events.length === 0) {
    tbody.innerHTML = `
      <tr class="${ECONOMIC_CALENDAR.error ? 'calendar-empty-row' : 'calendar-loading-row'}">
        <td colspan="7" class="${ECONOMIC_CALENDAR.error ? 'calendar-error' : ''}">
          ${escapeHtml(ECONOMIC_CALENDAR.error || "Loading this week's red-folder events...")}
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
    <div class="index-card" style="animation-delay: ${0.1 + i * 0.05}s">
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
  grid.innerHTML = DASHBOARD_DATA.tickers.map((t, i) => `
    <div class="ticker-card ${t.star ? 'star-pick' : ''}" style="animation-delay: ${0.15 + i * 0.04}s">
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

      <div class="chart-container" onclick="window.open('${getTradingViewUrl(t.ticker)}', '_blank')" title="Open ${t.ticker} on TradingView">
        <canvas class="sparkline-canvas" data-ticker="${t.ticker}"></canvas>
      </div>

      <div class="rsi-bar-container">
        <div class="rsi-bar-header">
          <span class="rsi-bar-label">RSI (14)</span>
          <span class="rsi-bar-value ${getRsiClass(t.rsi)}">${t.rsi}</span>
        </div>
        <div class="rsi-bar-track">
          <div class="rsi-bar-fill ${getRsiClass(t.rsi)}" style="width: ${t.rsi}%;"></div>
        </div>
      </div>

      <div class="atr-row">
        <div class="atr-item">
          <span class="atr-label">ATR</span>
          <span class="atr-value glow-hover">${t.atr}</span>
        </div>
        <div class="atr-item">
          <span class="atr-label">ATR %</span>
          <span class="atr-value glow-hover">${t.atrPct}%</span>
        </div>
        <div class="atr-item">
          <span class="atr-label">Exp Move</span>
          <span class="atr-value glow-hover">${escapeHtml(t.expectedMove)}</span>
        </div>
      </div>

      <table class="levels-table">
        <tr>
          <td>Prev Day High</td>
          <td>${formatPrice(t.prevDayHigh)}</td>
        </tr>
        <tr>
          <td>Prev Day Low</td>
          <td>${formatPrice(t.prevDayLow)}</td>
        </tr>
        <tr>
          <td>5-Day High</td>
          <td>${formatPrice(t.fiveDayHigh)}</td>
        </tr>
        <tr>
          <td>5-Day Low</td>
          <td>${formatPrice(t.fiveDayLow)}</td>
        </tr>
        <tr>
          <td>Support</td>
          <td class="support-vals">${t.support.join(' / ')}</td>
        </tr>
        <tr>
          <td>Resistance</td>
          <td class="resistance-vals">${t.resistance.join(' / ')}</td>
        </tr>
      </table>

      <div class="ticker-triggers">
        <div class="trigger trigger-bull">▲ ${escapeHtml(t.bullTrigger)}</div>
        <div class="trigger trigger-bear">▼ ${escapeHtml(t.bearTrigger)}</div>
      </div>

      <div class="ticker-meta">
        <div class="meta-row">
          <span class="meta-label">Options</span>
          <span class="meta-value">${escapeHtml(t.optionsIdea)}</span>
        </div>
      </div>

      <div class="ticker-summary">${escapeHtml(t.summary)}</div>
    </div>
  `).join('');
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
    >
      <td style="color: var(--text-muted); font-weight:700;">${w.rank}</td>
      <td style="color: var(--text-bright); font-weight:700;">${escapeHtml(w.ticker)}</td>
      <td class="${w.direction === 'LONG' ? 'direction-long' : 'direction-short'}">${escapeHtml(w.direction)}</td>
      <td>${escapeHtml(w.entry)}</td>
      <td>${escapeHtml(w.target)}</td>
      <td style="color: var(--red);">${escapeHtml(w.stop)}</td>
      <td style="color: var(--text-secondary);">${escapeHtml(w.catalyst)}</td>
    </tr>
  `).join('');
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
    return `<tr class="options-flow-loading"><td colspan="5">No ATM spread data available.</td></tr>`;
  }

  return rows.map((row) => {
    const statusClass = row.isWide ? 'wide' : 'ok';
    const statusText = row.isWide ? `Avoid > $${maxSpreadDollars.toFixed(2)}` : 'Tradeable';

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

  if (OPTIONS_FLOW.loading) {
    unusualBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">Loading Barchart options activity...</td></tr>`;
    mostActiveBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">Loading Barchart options activity...</td></tr>`;
    atmSpreadBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">Loading Barchart ATM spreads...</td></tr>`;
    meta.textContent = 'Loading Barchart options activity...';
    return;
  }

  if (OPTIONS_FLOW.error) {
    unusualBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">${escapeHtml(OPTIONS_FLOW.error)}</td></tr>`;
    mostActiveBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">${escapeHtml(OPTIONS_FLOW.error)}</td></tr>`;
    atmSpreadBody.innerHTML = `<tr class="options-flow-loading"><td colspan="5">${escapeHtml(OPTIONS_FLOW.error)}</td></tr>`;
    meta.textContent = 'Barchart feed unavailable';
    return;
  }

  atmSpreadBody.innerHTML = renderAtmSpreadRows(OPTIONS_FLOW.atmSpreads, OPTIONS_FLOW.maxSpreadDollars);
  unusualBody.innerHTML = renderOptionsFlowRows(OPTIONS_FLOW.unusual, 'unusual');
  mostActiveBody.innerHTML = renderOptionsFlowRows(OPTIONS_FLOW.mostActive, 'active');
  meta.textContent = OPTIONS_FLOW.updatedAt
    ? `Source: Barchart · ATM liquidity threshold $${OPTIONS_FLOW.maxSpreadDollars.toFixed(2)} · Updated ${OPTIONS_FLOW.updatedAt}`
    : 'Source: Barchart';
}

async function fetchOptionsFlow() {
  OPTIONS_FLOW.loading = true;
  renderOptionsFlow();

  try {
    const response = await fetch('/api/options-flow');
    if (!response.ok) {
      throw new Error('Options activity proxy unavailable.');
    }

    const payload = await response.json();
    OPTIONS_FLOW.unusual = payload.unusual || [];
    OPTIONS_FLOW.mostActive = payload.mostActive || [];
    OPTIONS_FLOW.atmSpreads = payload.atmSpreads || [];
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
    OPTIONS_FLOW.maxSpreadDollars = 0.15;
    OPTIONS_FLOW.loading = false;
    OPTIONS_FLOW.error = 'Use server.py to load live Barchart options activity.';
    OPTIONS_FLOW.updatedAt = '';
  }

  renderOptionsFlow();
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
        <div class="ticker-detail-panel-title">Price Structure</div>
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

function openTickerDetailModal(ticker) {
  const tickerData = getTickerDetails(ticker);
  if (!tickerData) return;

  const modal = document.getElementById('tickerDetailModal');
  const title = document.getElementById('tickerDetailTitle');
  const subtitle = document.getElementById('tickerDetailSubtitle');
  const body = document.getElementById('tickerDetailBody');

  title.textContent = tickerData.ticker;
  subtitle.textContent = tickerData.name || 'Trading detail';
  body.innerHTML = renderTickerDetailBody(tickerData);
  modal.classList.add('active');

  requestAnimationFrame(() => {
    const canvas = body.querySelector('.ticker-detail-canvas');
    const data = CHART_DATA[tickerData.ticker];
    const levels = getLevelsForTicker(tickerData.ticker);
    if (canvas && data) drawCandlestickChart(canvas, data, levels);
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

// In-memory storage for custom tickers (persists within session)
let customTickersList = loadGuestTickers();

async function fetchPublicAuthConfig() {
  const response = await fetch('/api/public-config', { cache: 'no-store' });
  if (!response.ok) {
    throw new Error('Auth config unavailable');
  }
  return response.json();
}

function renderGoogleButton() {
  const mount = document.getElementById('googleSignInMount');
  if (!mount || !AUTH_STATE.googleClientId || !window.google?.accounts?.id || AUTH_STATE.user) return;

  mount.innerHTML = '';
  window.google.accounts.id.initialize({
    client_id: AUTH_STATE.googleClientId,
    callback: handleGoogleCredentialResponse,
    auto_select: false,
    cancel_on_tap_outside: true,
  });
  window.google.accounts.id.renderButton(mount, {
    theme: 'outline',
    size: 'medium',
    shape: 'pill',
    text: 'signin_with',
    width: 180,
  });
  AUTH_STATE.buttonRendered = true;
}

function handleGoogleCredentialResponse(response) {
  try {
    const payload = decodeJwtPayload(response.credential);
    AUTH_STATE.user = {
      name: payload.name || '',
      email: payload.email || '',
      picture: payload.picture || '',
      sub: payload.sub || '',
    };
    saveStoredGoogleUser(AUTH_STATE.user);
    renderAuthControls();
    renderCustomTickers();
  } catch (error) {
    AUTH_STATE.error = 'Google sign-in failed';
    renderAuthControls();
  }
}

function persistTicker() {
  saveGuestTickers();
  return true;
}

function deleteTicker() {
  saveGuestTickers();
  return true;
}

async function initAuth(forceRefresh = false) {
  if (AUTH_STATE.configLoaded && !forceRefresh) {
    renderAuthControls();
    return;
  }

  AUTH_STATE.error = '';
  AUTH_STATE.configLoaded = false;
  AUTH_STATE.googleClientId = "";
  AUTH_STATE.user = loadStoredGoogleUser();
  renderAuthControls();

  try {
    const config = await fetchPublicAuthConfig();
    AUTH_STATE.configLoaded = true;
    AUTH_STATE.googleClientId = config.googleClientId || "";
    renderAuthControls();
  } catch (error) {
    AUTH_STATE.configLoaded = true;
    AUTH_STATE.error = 'Auth unavailable';
    renderAuthControls();
  }
}

async function signOut() {
  AUTH_STATE.user = null;
  saveStoredGoogleUser(null);
  if (window.google?.accounts?.id) {
    window.google.accounts.id.disableAutoSelect();
  }
  renderAuthControls();
  renderCustomTickers();
}

function addCustomTicker(symbol) {
  const ticker = symbol.toUpperCase().trim();
  if (!ticker || ticker.length > 5) return false;
  
  // Check if already in dashboard data
  const allExisting = [
    ...DASHBOARD_DATA.indexes.map(i => i.ticker),
    ...DASHBOARD_DATA.tickers.map(t => t.ticker)
  ];
  if (allExisting.includes(ticker)) return 'exists';
  
  // Check if already in custom list
  if (customTickersList.includes(ticker)) return 'duplicate';
  
  customTickersList.push(ticker);
  return ticker;
}

async function removeCustomTicker(ticker) {
  customTickersList = customTickersList.filter(t => t !== ticker);
  deleteTicker(ticker);
  renderCustomTickers();
}

function renderCustomTickers() {
  const grid = document.getElementById('customTickerGrid');
  // Filter out tickers that are now in the main dashboard data
  const mainTickers = [
    ...DASHBOARD_DATA.indexes.map(i => i.ticker),
    ...DASHBOARD_DATA.tickers.map(t => t.ticker)
  ];
  const filtered = customTickersList.filter(t => !mainTickers.includes(t));
  customTickersList = filtered;
  
  if (filtered.length === 0) {
    grid.style.display = 'none';
    return;
  }
  
  grid.style.display = 'block';
  grid.innerHTML = `
    <div class="custom-ticker-label">Custom Tickers</div>
    ${filtered.map((ticker, i) => `
      <div class="custom-card" style="animation-delay: ${i * 0.05}s; margin-bottom: 8px;">
        <div class="custom-card-info">
          <span class="custom-card-ticker" onclick="window.open('${getTradingViewUrl(ticker)}', '_blank')" title="Open ${escapeHtml(ticker)} on TradingView">
            ${escapeHtml(ticker)} <span style="font-size:0.65rem; color:var(--text-muted);">↗</span>
          </span>
          <span class="custom-card-status">Added to tracking — ${AUTH_STATE.user ? 'saved on this browser for your Google session' : 'saved on this browser'}</span>
        </div>
        <div class="custom-card-actions">
          <a class="custom-card-tv" href="${getTradingViewUrl(ticker)}" target="_blank" rel="noopener">TradingView</a>
          <button class="custom-card-remove" onclick="removeCustomTicker('${escapeHtml(ticker)}')" title="Remove ${escapeHtml(ticker)}">×</button>
        </div>
      </div>
    `).join('')}
  `;
}

// Modal logic
function initAddTickerModal() {
  const modal = document.getElementById('addTickerModal');
  const btn = document.getElementById('addTickerBtn');
  const input = document.getElementById('tickerInput');
  const addBtn = document.getElementById('modalAdd');
  const cancelBtn = document.getElementById('modalCancel');
  const closeBtn = document.getElementById('modalClose');
  
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
  }
  
  btn.addEventListener('click', openModal);
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
// Live Market Data
// ============================================

async function fetchMarketData() {
  try {
    const response = await fetch('/api/market-data');
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
    }

    // Re-render all data-driven sections
    renderHeader();
    renderIndexCards();
    renderTickerCards();
    renderWatchlist();
    renderCustomTickers();

    // Update footer disclaimer
    const footer = document.querySelector('.footer-disclaimer');
    if (footer && payload.updatedAt) {
      const t = new Date(payload.updatedAt * 1000);
      footer.textContent = `Live data as of ${t.toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric'
      })} ${t.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}. `
        + 'Indicators computed from Yahoo Finance daily bars. Not financial advice.';
    }

    // Redraw sparkline charts with live OHLCV
    requestAnimationFrame(() => initAllCharts());

  } catch (err) {
    // Silent fail — static dashboard data remains visible
    console.warn('[Option Riders] Live market data unavailable:', err.message);
  }
}

// ============================================
// Initialize
// ============================================

async function init() {
  await initAuth();
  renderHeader();
  renderAuthControls();
  renderAlertBar();
  renderCatalysts();
  renderCalendar();
  renderIndexCards();
  renderTickerCards();
  renderWatchlist();
  renderThemes();
  renderCustomTickers();
  renderOptionsFlow();
  initCollapsibleSections();
  initAddTickerModal();
  initTickerDetailModal();
  await Promise.allSettled([
    fetchEconomicCalendar(),
    fetchOptionsFlow(),
    fetchMarketData(),
  ]);
  // Draw sparkline charts after DOM is ready (live data already merged above if available)
  requestAnimationFrame(() => initAllCharts());
}

// Run on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
