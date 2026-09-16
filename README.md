# Option Riders

Option Riders is a live intraday trading dashboard focused on high-signal watchlists, USD red-folder macro events, and Barchart-powered options flow.

## Features

- Quick watchlist with click-through ticker detail modal
- Weekly USD high-impact economic calendar
- Local-time NYSE market open badge with DST-safe conversion
- Sticky top warning bar for key daily and weekly risks
- Barchart unusual options, most traded options, and ATM spread checks

## Local development

Run the local dashboard server:

```bash
python3 server.py
```

Open:

```text
http://127.0.0.1:8125
```

## Deployment

This project is set up for Vercel:

- Static frontend served from the repo root
- Barchart proxy exposed through `api/options-flow.py`
- public auth config exposed through `api/public-config.py`
- Routing configured in `vercel.json`

## Accounts

Option Riders supports lightweight Google sign-in in the browser.

Set this environment variable in Vercel and locally before using sign-in:

```text
GOOGLE_CLIENT_ID=
```

Google setup:

1. In Google Cloud Console, create or select a project.
2. Open `APIs & Services` -> `Credentials`.
3. Create an `OAuth client ID` for a `Web application`.
4. Add these `Authorized JavaScript origins`:
   `http://127.0.0.1:8125`
   `http://localhost:8125`
   `https://www.optionriders.com`
5. Copy the client ID into `.env` locally and into your Vercel project environment variables as `GOOGLE_CLIENT_ID`.
6. Restart the local server after updating `.env`.

The current app uses Google Identity Services in the browser and stores the signed-in profile locally for dashboard access.

To enable the TradingView script checkout CTA, also set:

```text
STRIPE_PAYMENT_LINK=
TRADINGVIEW_PRODUCT_NAME=
TRADINGVIEW_PRODUCT_DESCRIPTION=
TRADINGVIEW_PRODUCT_PRICE_LABEL=
TRADINGVIEW_MONTHLY_LINK=
TRADINGVIEW_MONTHLY_NAME=
TRADINGVIEW_MONTHLY_PRICE=
TRADINGVIEW_MONTHLY_DESCRIPTION=
TRADINGVIEW_LIFETIME_LINK=
TRADINGVIEW_LIFETIME_NAME=
TRADINGVIEW_LIFETIME_PRICE=
TRADINGVIEW_LIFETIME_DESCRIPTION=
```

User-added tickers remain saved in local browser storage.

## Domain

Intended production domain:

```text
https://www.optionriders.com
```

---

## Dashboard Subscription Setup (Supabase + Stripe)

The dashboard is gated behind a real backend subscription check. Access is granted when the Supabase `dashboard_subscriptions` table shows `status = trialing` or `active` for the signed-in user.

### Required environment variables

**Supabase (add to `.env` and Vercel project settings):**

```text
SUPABASE_URL=               # e.g. https://abcxyz.supabase.co
SUPABASE_ANON_KEY=          # safe to expose in frontend — anon key only
SUPABASE_SERVICE_ROLE_KEY=  # server-side only — never expose in the browser
```

**Stripe (add to `.env` and Vercel project settings):**

```text
STRIPE_SECRET_KEY=              # sk_live_... (use sk_test_... for local dev)
STRIPE_WEBHOOK_SECRET=          # whsec_... from Stripe Dashboard → Webhooks
STRIPE_DASHBOARD_PRICE_ID=      # price_... recurring price for dashboard sub
DASHBOARD_TRIAL_DAYS=7          # free trial length in days (default: 7)
APP_URL=https://www.optionriders.com   # base URL for Stripe redirect_url
```

### Supabase setup

1. Create a new Supabase project at https://supabase.com.
2. In the Supabase **SQL Editor**, run the migration file:
   ```
   supabase/migrations/20240001_dashboard_subscriptions.sql
   ```
3. In **Authentication → Providers → Google**, enable Google OAuth and paste
   your Google OAuth Client ID + Secret (same credentials used before).
4. Under **Authentication → URL Configuration**, add the following to
   **Redirect URLs**:
   - `http://127.0.0.1:8125/`
   - `https://www.optionriders.com/`
5. Copy `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`
   from **Project Settings → API** into your `.env` and Vercel environment.

### Stripe dashboard setup

1. In Stripe, create a **Product** called "Option Riders Dashboard".
2. Add a **recurring price** (e.g. $19/month) and copy the `price_...` ID
   into `STRIPE_DASHBOARD_PRICE_ID`.
3. Go to **Developers → Webhooks** and add an endpoint:
   - URL: `https://www.optionriders.com/api/stripe-webhook`
   - Events to send:
     - `checkout.session.completed`
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
4. Copy the **Signing secret** (`whsec_...`) into `STRIPE_WEBHOOK_SECRET`.
5. Enable the **Billing Portal** at **Settings → Billing → Customer portal**
   (required for `openBillingPortal()` to work).

### Testing locally

1. Install dependencies:
   ```bash
   pip install stripe requests
   ```
2. Copy `.env` with real test values (`sk_test_...`, test Supabase project).
3. Start the server:
   ```bash
   python3 server.py
   ```
4. Forward Stripe webhooks to your local server using the Stripe CLI:
   ```bash
   stripe listen --forward-to http://127.0.0.1:8125/api/stripe-webhook
   ```
   The CLI prints a `whsec_...` secret — set that as `STRIPE_WEBHOOK_SECRET`
   in `.env` for local testing.
5. Open http://127.0.0.1:8125, sign in with Google, and click
   **Start Free Trial** to test the full checkout flow.

### Access control logic

| User state | Dashboard | Gate shown |
|---|---|---|
| Not signed in | Locked | Sign-in card |
| Signed in, `status = none / canceled / past_due` | Locked | Subscribe / trial CTA |
| Signed in, `status = trialing` | Unlocked | Nothing (hidden) |
| Signed in, `status = active` | Unlocked | Nothing (hidden) |

Access is always verified server-side via `/api/subscription-status` — the
frontend cannot self-grant access by manipulating local state.

## Journal trade chart

Opening a trade shows the underlying's five-minute candles with green Entry
arrows and red Exit arrows for its executions, including partial fills. Arrows
attach to the candle containing the execution; the labels and execution strip
show the contract fill prices, not the underlying price. Times use Europe/London
with daylight-saving conversion from IBKR's New York timestamps. For overnight
trades, the chart includes each session containing an execution.

Historical candles come from Alpha Vantage using the requested trade month. If
that returns no data, recent sessions fall back to Yahoo Finance through the
existing yfinance dependency. Older dates require historical intraday access
from Alpha Vantage. Missing candles are explicitly identified; executions are
never snapped to unrelated candles. When all candles are unavailable, exact
execution times remain visible above a clearly labelled live reference chart.

Regression checks:

```bash
node tests/journal-chart.cjs
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Personal monthly target

The Monthly Target panel lets each user set a monthly amount and planned trading
days (20 by default). Daily target = monthly target / planned trading days. The
progress pie, daily target, brick wall and Why I Trade breakdown all use the saved
plan. One brick represents one planned day's target; the wall is complete when
the monthly target is reached. Targets use the journal's display currency.

Signed-in users save preferences in their own Supabase user metadata, separately
for each display currency, so the plan loads across devices without a database
migration. Local mode without Supabase saves in that browser. Failed account
saves display an error and keep the previous plan. The target persists across
months; monthly profit progress resets each month as before.

Run the target regression checks with `node tests/journal-goal.cjs`.

## Intraday screening quality

Top Trade Today shows up to four qualifying **watchlist** setups; it no longer
adds filler trades. Setup points are heuristic ranking points, not a calibrated
success probability. The ranking weights have not been optimized or validated
against future returns. Existing daily-horizon backtest statistics elsewhere in
the dashboard do not validate this intraday options screen.

Screening now requires aligned, finite, completed OHLCV rows with timestamps,
21 bars of history on the 2-minute and 15-minute frames, and current-session
candles. Their latest starts must be no more than one candle duration plus eight
minutes old. Hourly bars use regular hours. The derived four-hour context uses
only complete 09:30–13:30 blocks; it never combines adjacent trading days and
omits shortened sessions.

The option quote must match the selected call/put side, have a positive bid and
non-crossed ask, a non-expired date, and a spread no greater than 10% of midpoint.
The 10% ceiling is a conservative screening policy, not a statistically optimized
value. Source snapshots older than 15 minutes are excluded. Cards use the actual
ATM contract returned by the feed instead of constructing a strike and Friday
expiry. The feed's retrieval timestamp does not establish quote freshness;
exchange quote timestamps and delta remain unavailable and must be checked in
a broker quote before execution.

Stops must be on the loss side of the entry and profit targets strictly beyond
it. Missing levels exclude a setup instead of generating ATR-based targets.
Displayed reward/risk is the first **underlying-price** target distance divided
by stop distance; it is not the option contract's expected return. ATR is labelled
as historical daily range, and relative strength as a five-day measure.

The scan uses the [published NYSE equity-session calendar](https://www.nyse.com/trade/hours-calendars)
for 2026–2028, including holidays and early closes. Extend the calendar before
2029; unknown years fail closed. Unscheduled exchange closures are not encoded,
so current-session data checks remain necessary. Scanning ends at the underlying
regular-session close even where some options trade later.

The visible page checks for a new scan every five minutes; requests are guarded
against overlap and failed requests have a five-minute retry interval. Refresh
picks starts a manual refresh. Missing data and stale results are identified.

Validation: `python3 -m unittest discover -s tests -p 'test_*.py'` and
`node tests/top-trade-ui.cjs`. These verify correctness, not trading performance.
A performance study should preserve point-in-time input snapshots and compare
subsequent outcomes on held-out sessions, including bid/ask costs and slippage,
before changing weights or presenting a measured success rate.
