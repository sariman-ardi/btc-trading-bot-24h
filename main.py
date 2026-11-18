"""BTC trend bot for make.fun "Race a BTC trading bot live for 24 hours".

Strategy (own design, tuned on the dev window only):
  - Long only, one position at a time, full size in two steps (scale-in).
  - Entry: fast EMA (20) crosses above slow EMA (120) AND the trailing
    60-minute return is positive. Buy half the cash.
  - Add: when the EMA spread widens past 30 bps of the close while still
    widening, spend the rest of the cash (the trend has confirmed itself;
    false breakouts in chop rarely widen that far, so they stay half size).
  - Exit: take profit +200 bps from the first entry close, hard stop -150 bps,
    EMA cross back down, or 600 bars held. 15-bar cooldown after an exit.
  - No entries in the final 30 bars of the 1,440-bar window.
  - Never trades during warm-up bars.
  - Guardrail fallback: if no order has ever filled by bar 1,380, buy the
    minimum notional (1 USDC) once and hold it to the final flatten, so the
    entry always has at least one trade on the race window.

Everything is a pure function of the bars seen so far: no clock, no network,
no files, no randomness. EMAs use float64 arithmetic in a fixed order, so two
runs answer byte for byte the same.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
BPS = 10_000
WINDOW_BARS = 1_440

EMA_FAST = 20
EMA_SLOW = 120
MOM_BARS = 60
MOM_MIN_BPS = 0
ADD_SPREAD_BPS = 30
TAKE_PROFIT_BPS = 200
STOP_BPS = 150
MAX_HOLD_BARS = 600
COOLDOWN_BARS = 15
MIN_HISTORY_BARS = 120
NO_ENTRY_LAST_BARS = 30
MAX_SLIPPAGE_BPS = 150
FALLBACK_SEQ = 1_380
FALLBACK_NOTIONAL = 1_000_000  # 1 USDC, the minimum notional


class Bot:
    def __init__(self):
        self.ema_fast = None
        self.ema_slow = None
        self.alpha_fast = 2.0 / (EMA_FAST + 1)
        self.alpha_slow = 2.0 / (EMA_SLOW + 1)
        self.prev_diff = 0.0
        self.closes = []
        self.in_position = False
        self.added = False
        self.entry_close = 0
        self.entry_seq = 0
        self.cool_until = -1
        self.warmup_bars = 0
        self.fills = 0
        self.fallback = False

    def on_hello(self, state):
        self.warmup_bars = state.hello.get("warmup_bars", 0)

    def on_batch(self, state, batch):
        for fill in batch.get("fills") or []:
            if fill.get("status") == "filled":
                self.fills += 1
        if state.warming_up:
            return []
        close = state.close(SYMBOL)
        if close is None:
            return []
        self.closes.append(close)
        if self.ema_fast is None:
            self.ema_fast = float(close)
            self.ema_slow = float(close)
        else:
            self.ema_fast += self.alpha_fast * (close - self.ema_fast)
            self.ema_slow += self.alpha_slow * (close - self.ema_slow)
        diff = self.ema_fast - self.ema_slow
        spread_bps = diff * BPS / close
        seq = state.seq

        if self.in_position:
            if self.fallback:
                # Guardrail position: hold to the final flatten, no exits.
                return []
            held = seq - self.entry_seq
            exit_now = False
            if close * BPS < self.entry_close * (BPS - STOP_BPS):
                exit_now = True
            if close * BPS > self.entry_close * (BPS + TAKE_PROFIT_BPS):
                exit_now = True
            if held >= MAX_HOLD_BARS:
                exit_now = True
            if diff < 0:
                exit_now = True
            if exit_now:
                self.in_position = False
                self.added = False
                self.cool_until = seq + COOLDOWN_BARS
                holding = state.positions.get(SYMBOL)
                if holding is None or holding.qty <= 0:
                    return []
                return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            if not self.added and spread_bps > ADD_SPREAD_BPS and diff > self.prev_diff:
                self.added = True
                self.prev_diff = diff
                if state.cash > 0:
                    return [{"side": "buy", "symbol": SYMBOL,
                             "notional_quote_units": state.cash,
                             "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            self.prev_diff = diff
            return []

        # Flat: maybe enter. While blocked (too little history, too close to
        # the end, or cooling down) prev_diff is deliberately NOT updated:
        # an entry needs a fresh cross-up after the block ends, not one
        # that happened while entry was impossible.
        if len(self.closes) < MIN_HISTORY_BARS:
            return []
        last_entry_seq = self.warmup_bars + WINDOW_BARS - NO_ENTRY_LAST_BARS
        if seq >= last_entry_seq:
            return []
        if seq < self.cool_until:
            return []
        if not self.fallback and self.fills == 0 and seq >= self.warmup_bars + FALLBACK_SEQ:
            # Guardrail fallback: no fill at all by bar ~1,380, so buy the
            # minimum notional once and hold it to the final flatten.
            self.in_position = True
            self.fallback = True
            self.entry_close = close
            self.entry_seq = seq
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": FALLBACK_NOTIONAL,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        crossed = self.prev_diff <= 0 and diff > 0
        self.prev_diff = diff
        if not crossed:
            return []
        if len(self.closes) > MOM_BARS:
            mom = (close - self.closes[-MOM_BARS - 1]) * BPS // self.closes[-MOM_BARS - 1]
            if mom < MOM_MIN_BPS:
                return []
        if state.cash <= 0:
            return []
        self.in_position = True
        self.added = False
        self.entry_close = close
        self.entry_seq = seq
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": state.cash // 2,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def main():
    bot = Bot()
    makefun_bars.run(bot.on_batch, on_hello=bot.on_hello)


if __name__ == "__main__":
    main()
