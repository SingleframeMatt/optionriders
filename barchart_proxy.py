import http.cookiejar
import json
import threading
import time
import urllib.parse
import urllib.request


CACHE_TTL_SECONDS = 60
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
BARCHART_PAGE = "https://www.barchart.com/options"
BARCHART_API_ROOT = "https://www.barchart.com/proxies/core-api/v1"
WATCHLIST_SYMBOLS = ["SPY", "QQQ", "NVDA", "MU", "META", "AAPL", "AVGO"]
MAX_SPREAD_DOLLARS = 0.15

cache_lock = threading.Lock()
options_cache = {"expires_at": 0.0, "payload": None}


def build_barchart_opener():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", USER_AGENT)]
    opener.open(BARCHART_PAGE, timeout=20).read()

    xsrf_token = ""
    for cookie in jar:
        if cookie.name == "XSRF-TOKEN":
            xsrf_token = urllib.parse.unquote(cookie.value)
            break

    return opener, xsrf_token


def fetch_json(opener, xsrf_token, path, referer):
    req = urllib.request.Request(
        f"{BARCHART_API_ROOT}{path}",
        headers={
            "User-Agent": USER_AGENT,
            "X-XSRF-TOKEN": xsrf_token,
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )
    with opener.open(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get_option_side(symbol):
    contract = symbol.split("|")[-1]
    if contract.endswith("C"):
        return "Call"
    if contract.endswith("P"):
        return "Put"
    return "Option"


def normalize_unusual_rows(rows):
    stock_rows = [row for row in rows if row.get("baseSymbolType") == 1]
    normalized = []

    for row in stock_rows[:5]:
        normalized.append({
            "baseSymbol": row.get("baseSymbol", ""),
            "symbol": row.get("symbol", ""),
            "contract": f"{row.get('strikePrice', '—')} {get_option_side(row.get('symbol', ''))}",
            "expirationDate": row.get("expirationDate", "—"),
            "premium": row.get("premium", "—"),
            "tradeSize": row.get("tradeSize", "—"),
            "sentiment": row.get("sentiment", "Neutral"),
            "volume": row.get("volume", "—"),
            "openInterest": row.get("openInterest", "—"),
        })

    return normalized


def normalize_most_active_rows(rows):
    normalized = []

    for row in rows[:5]:
        normalized.append({
            "baseSymbol": row.get("baseSymbol", ""),
            "symbol": row.get("symbol", ""),
            "contract": f"{row.get('strikePrice', '—')} {row.get('optionType', 'Option')}",
            "expirationDate": row.get("expirationDate", "—"),
            "lastPrice": row.get("lastPrice", "—"),
            "volume": row.get("volume", "—"),
            "openInterest": row.get("openInterest", "—"),
        })

    return normalized


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_money(value):
    if value is None:
        return "—"
    return f"${value:.2f}"


def pick_atm_contract(rows, option_type):
    candidates = []

    for row in rows:
        if row.get("optionType") != option_type:
            continue

        strike = to_float(row.get("strikePrice"))
        base_price = to_float(row.get("baseLastPrice"))
        bid = to_float(row.get("bidPrice"))
        ask = to_float(row.get("askPrice"))

        if strike is None or base_price is None or bid is None or ask is None or ask < bid:
            continue

        spread = ask - bid
        distance = abs(strike - base_price)
        candidates.append((distance, spread, row))

    if not candidates:
        return None

    _, _, best_row = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    return best_row


def build_spread_entry(row):
    if not row:
        return {
            "contract": "—",
            "expirationDate": "—",
            "bid": "—",
            "ask": "—",
            "spread": None,
            "spreadLabel": "—",
        }

    bid = to_float(row.get("bidPrice"))
    ask = to_float(row.get("askPrice"))
    spread = ask - bid if bid is not None and ask is not None else None

    return {
        "contract": f"{row.get('strikePrice', '—')} {row.get('optionType', 'Option')}",
        "expirationDate": row.get("expirationDate", "—"),
        "bid": format_money(bid),
        "ask": format_money(ask),
        "spread": spread,
        "spreadLabel": format_money(spread),
    }


def fetch_atm_spreads(opener, xsrf_token):
    spreads = []

    for symbol in WATCHLIST_SYMBOLS:
        chain = fetch_json(
            opener,
            xsrf_token,
            f"/options/get?raw=1&baseSymbol={urllib.parse.quote(symbol)}&expirationDate=nearest&fields=symbol,baseSymbol,optionType,strikePrice,expirationDate,bidPrice,askPrice,lastPrice,baseLastPrice,volume,openInterest&orderBy=strikePrice&orderDir=asc&limit=200",
            BARCHART_PAGE,
        )

        rows = chain.get("data", [])
        call_row = pick_atm_contract(rows, "Call")
        put_row = pick_atm_contract(rows, "Put")
        reference_row = call_row or put_row or {}
        underlying_price = to_float(reference_row.get("baseLastPrice"))
        call_spread = build_spread_entry(call_row)
        put_spread = build_spread_entry(put_row)
        widest_spread = max(
            [value for value in (call_spread["spread"], put_spread["spread"]) if value is not None],
            default=None,
        )

        spreads.append({
            "ticker": symbol,
            "underlyingPrice": format_money(underlying_price),
            "call": call_spread,
            "put": put_spread,
            "widestSpread": widest_spread,
            "widestSpreadLabel": format_money(widest_spread),
            "isWide": widest_spread is not None and widest_spread > MAX_SPREAD_DOLLARS,
        })

    return spreads


def fetch_options_activity():
    now = time.time()

    with cache_lock:
        if options_cache["payload"] and options_cache["expires_at"] > now:
            return options_cache["payload"]

    opener, xsrf_token = build_barchart_opener()

    unusual = fetch_json(
        opener,
        xsrf_token,
        "/options/flow?raw=1&limit=100&fields=symbol,baseSymbol,baseSymbolType,strikePrice,expirationDate,tradeSize,premium,sentiment,volume,openInterest",
        BARCHART_PAGE,
    )
    most_active = fetch_json(
        opener,
        xsrf_token,
        "/options/get?raw=1&limit=5&baseSymbolType=stock&orderBy=volume&orderDir=desc&fields=symbol,baseSymbol,baseSymbolType,optionType,strikePrice,expirationDate,lastPrice,volume,openInterest",
        BARCHART_PAGE,
    )

    payload = {
        "source": "Barchart",
        "updatedAt": int(now),
        "unusual": normalize_unusual_rows(unusual.get("data", [])),
        "mostActive": normalize_most_active_rows(most_active.get("data", [])),
        "atmSpreads": fetch_atm_spreads(opener, xsrf_token),
        "maxSpreadDollars": MAX_SPREAD_DOLLARS,
    }

    with cache_lock:
        options_cache["payload"] = payload
        options_cache["expires_at"] = now + CACHE_TTL_SECONDS

    return payload
