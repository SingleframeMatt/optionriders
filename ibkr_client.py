#!/usr/bin/env python3
"""
ibkr_client.py — ib_insync wrapper for the options trading bot.

Responsibilities:
  - Connect / auto-reconnect to IBKR TWS/Gateway paper trading
  - Fetch historical 5-minute bars for underlyings
  - Look up ATM option contracts within a DTE window
  - Place limit buy/sell orders and await fills
  - Return account summary (paper balance, daily P&L)

All IBKR calls are async (ib_insync uses asyncio internally).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pytz
from ib_insync import IB, Index, LimitOrder, Option, Stock, util

log = logging.getLogger("ibkr_client")

ET = pytz.timezone("America/New_York")


class IBKRClient:
    """
    Thin async wrapper around ib_insync.IB.

    Usage:
        client = IBKRClient(host="127.0.0.1", port=7497, client_id=1)
        await client.connect()
        bars = await client.get_bars("SPY", duration="2 D", bar_size="5 mins")
        await client.disconnect()
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        timeout: int = 20,
        readonly: bool = False,
    ):
        self.host      = host
        self.port      = port
        self.client_id = client_id
        self.timeout   = timeout
        self.readonly  = readonly
        self._ib: Optional[IB] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Connection management
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def ib(self) -> IB:
        if self._ib is None:
            self._ib = IB()
        return self._ib

    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    async def connect(self) -> bool:
        """Connect to IBKR. Returns True on success."""
        if self.is_connected():
            return True
        try:
            log.info("Connecting to IBKR %s:%d clientId=%d …", self.host, self.port, self.client_id)
            await self.ib.connectAsync(
                self.host, self.port,
                clientId=self.client_id,
                timeout=self.timeout,
                readonly=self.readonly,
            )
            log.info("Connected to IBKR paper trading.")
            return True
        except Exception as exc:
            log.error("IBKR connect failed: %s", exc)
            return False

    async def disconnect(self):
        """Gracefully disconnect."""
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            log.info("Disconnected from IBKR.")

    async def ensure_connected(self):
        """Re-connect if the socket dropped."""
        if not self.is_connected():
            await self.connect()

    # ─────────────────────────────────────────────────────────────────────────
    # Historical bars
    # ─────────────────────────────────────────────────────────────────────────

    async def get_bars(
        self,
        symbol: str,
        duration: str = "2 D",
        bar_size: str = "5 mins",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
    ) -> list:
        """
        Fetch historical bars for a stock/index underlying.
        For SPX use Index("SPX", "CBOE"); for SPY/QQQ use Stock(..., "SMART").
        Returns list of ib_insync BarData objects, newest last.
        """
        await self.ensure_connected()
        contract = self._make_underlying(symbol)
        try:
            bars = await self.ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=2,   # UTC timestamps
            )
            return bars or []
        except Exception as exc:
            log.error("get_bars failed for %s: %s", symbol, exc)
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Options chain / contract lookup
    # ─────────────────────────────────────────────────────────────────────────

    async def find_atm_option(
        self,
        symbol: str,
        right: str,          # "C" or "P"
        price: float,        # current underlying price
        min_dte: int = 2,
        max_dte: int = 5,
        max_premium: float = 200.0,
    ) -> Tuple[Optional[object], float]:
        """
        Find the best ATM option contract (2–5 DTE by default) with
        premium ≤ max_premium dollars (1 contract = 100 shares).

        Strategy:
          1. Try ATM strike, starting from min_dte expiry.
          2. If ATM is too expensive, try one strike further OTM.
          3. Return the first contract whose cost fits the budget.

        Returns (qualified_contract, mid_price_per_share) or (None, 0.0).
        """
        await self.ensure_connected()
        today = datetime.now(ET).date()

        # Build candidate expiry dates (weekdays only, min_dte … max_dte)
        expiries = []
        for dte in range(min_dte, max_dte + 1):
            exp = today + timedelta(days=dte)
            if exp.weekday() < 5:
                expiries.append(exp.strftime("%Y%m%d"))
        if not expiries:
            log.warning("No valid expiry dates found (min=%d max=%d)", min_dte, max_dte)
            return None, 0.0

        # Strike parameters
        step = self._strike_step(symbol)
        atm  = round(price / step) * step
        exchange   = "CBOE" if symbol == "SPX" else "SMART"
        currency   = "USD"
        multiplier = "100"

        # Try ATM, then one OTM
        strike_candidates = [atm]
        if right == "C":
            strike_candidates.append(atm + step)   # one OTM call
        else:
            strike_candidates.append(atm - step)   # one OTM put

        for strike in strike_candidates:
            for expiry in expiries:
                contract = Option(
                    symbol    = symbol,
                    lastTradeDateOrContractMonth = expiry,
                    strike    = strike,
                    right     = right,
                    exchange  = exchange,
                    currency  = currency,
                    multiplier= multiplier,
                )
                try:
                    details = await self.ib.reqContractDetailsAsync(contract)
                    if not details:
                        continue
                    qualified = details[0].contract
                    [ticker]  = await self.ib.reqTickersAsync(qualified)
                    bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0.0
                    ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0.0
                    mid = (bid + ask) / 2.0 if bid and ask else (ticker.last or 0.0)
                    cost = mid * 100.0
                    if 0.01 < cost <= max_premium:
                        log.info(
                            "Option found: %s %s %s %.0f @ $%.2f mid (cost $%.0f)",
                            symbol, expiry, right, strike, mid, cost,
                        )
                        return qualified, mid
                    else:
                        log.debug(
                            "Option %s %s %s %.0f cost $%.0f exceeds limit or zero",
                            symbol, expiry, right, strike, cost,
                        )
                except Exception as exc:
                    log.debug("Option lookup %s %s %.0f: %s", expiry, right, strike, exc)
                    continue

        log.warning("No affordable ATM option found for %s %s (budget $%.0f)", symbol, right, max_premium)
        return None, 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Order execution
    # ─────────────────────────────────────────────────────────────────────────

    async def buy_limit(
        self,
        contract,
        qty: int,
        limit_price: float,
        wait_secs: int = 30,
    ) -> Tuple[Optional[object], float]:
        """
        Place a limit BUY order and wait up to wait_secs for a fill.
        Returns (trade_object, avg_fill_price). fill_price is 0 if not filled.
        """
        await self.ensure_connected()
        order = LimitOrder("BUY", qty, round(limit_price, 2))
        trade = self.ib.placeOrder(contract, order)
        fill  = await self._await_fill(trade, wait_secs)
        if not fill:
            log.warning("BUY not filled in %ds — cancelling", wait_secs)
            try:
                self.ib.cancelOrder(order)
            except Exception:
                pass
            return trade, 0.0
        return trade, trade.orderStatus.avgFillPrice or limit_price

    async def sell_limit(
        self,
        contract,
        qty: int,
        limit_price: float,
        wait_secs: int = 30,
    ) -> Tuple[Optional[object], float]:
        """
        Place a limit SELL order and wait up to wait_secs for a fill.
        Returns (trade_object, avg_fill_price).
        """
        await self.ensure_connected()
        order = LimitOrder("SELL", qty, round(limit_price, 2))
        trade = self.ib.placeOrder(contract, order)
        fill  = await self._await_fill(trade, wait_secs)
        if not fill:
            log.warning("SELL not filled in %ds — cancelling", wait_secs)
            try:
                self.ib.cancelOrder(order)
            except Exception:
                pass
            return trade, 0.0
        return trade, trade.orderStatus.avgFillPrice or limit_price

    async def get_mid_price(self, contract) -> float:
        """Get the current mid price of an option contract."""
        await self.ensure_connected()
        try:
            [ticker] = await self.ib.reqTickersAsync(contract)
            bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0.0
            ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0.0
            if bid and ask:
                return (bid + ask) / 2.0
            return ticker.last or 0.0
        except Exception as exc:
            log.warning("get_mid_price failed: %s", exc)
            return 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Account data
    # ─────────────────────────────────────────────────────────────────────────

    async def get_account_summary(self) -> dict:
        """
        Returns a dict with NetLiquidation, AvailableFunds, UnrealizedPnL, RealizedPnL.
        Values are floats; keys are strings. Returns empty dict on failure.

        Cancels the subscription immediately after fetching to avoid IBKR
        Error 322 "Maximum number of account summary requests exceeded".
        """
        await self.ensure_connected()
        try:
            account_values = await self.ib.reqAccountSummaryAsync()
            # Cancel the subscription right away so we don't accumulate open requests
            try:
                self.ib.cancelAccountSummary()
            except Exception:
                pass
            out = {}
            for av in account_values:
                if av.tag in ("NetLiquidation", "AvailableFunds", "UnrealizedPnL", "RealizedPnL"):
                    try:
                        out[av.tag] = float(av.value)
                    except (ValueError, TypeError):
                        pass
            return out
        except Exception as exc:
            log.warning("get_account_summary failed: %s", exc)
            return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _make_underlying(self, symbol: str):
        """Build the correct Contract object for a given symbol."""
        if symbol == "SPX":
            return Index("SPX", "CBOE", "USD")
        return Stock(symbol, "SMART", "USD")

    @staticmethod
    def _strike_step(symbol: str) -> float:
        """Strike increment for ATM rounding."""
        if symbol == "SPX":
            return 5.0
        return 1.0   # SPY, QQQ

    @staticmethod
    async def _await_fill(trade, timeout: int) -> bool:
        """Poll trade status until filled or timeout."""
        for _ in range(timeout):
            await asyncio.sleep(1)
            status = trade.orderStatus.status
            if status == "Filled":
                return True
            if status in ("Cancelled", "ApiCancelled", "Inactive"):
                return False
        return False
