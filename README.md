# BTC Trend Bot — Race a BTC trading bot live for 24 hours

[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/sariman-ardi/btc-trading-bot-24h/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/sariman-ardi/btc-trading-bot-24h/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)

A long-only BTC (CBBTC/USDC) trading bot for make.fun's 24-hour live race.
It trades minute bars through the `agent-fun/bars-replay/v1` protocol, starts
with 1,000 USDC of paper money, and makes only a handful of trades: it waits
for a real multi-hour uptrend, scales in as the trend confirms itself, and
gets out on a take-profit, a hard stop, or the trend turning down.

## How it works

- **Trend filter.** Two EMAs of the close (20 and 120 minutes). The bot only
  looks for entries while the fast EMA is above the slow one.
- **Entry.** When the fast EMA crosses above the slow EMA *and* the trailing
  60-minute return is positive, it buys with half the cash.
- **Scale-in.** When the EMA spread widens past 30 bps of the close while
  still widening, it spends the rest of the cash. Breakouts in choppy markets
  rarely widen that far, so false entries stay half size.
- **Exit.** Take profit at +200 bps from the first entry close, hard stop at
  −150 bps, exit when the fast EMA crosses back below the slow one, or after
  600 bars held. 15-bar cooldown after every exit, no entries in the final
  30 bars of the window, and no trading during warm-up bars.
- **Costs respected.** A full round trip costs about 26 bps (4 bps fee,
  2 bps slippage, ~20 bps of pool impact on a full-size trade), so the bot
  never scalps: 1-minute noise is only ~7 bps of standard deviation, far
  below the round-trip cost. Every trade has to catch a move of 200 bps or
  it does not happen.
- **Deterministic.** The bot is a pure function of the bars seen so far: no
  clock, no network, no files, no randomness. Two runs answer byte for byte
  the same.

## Backtest — dev window (2026-11-17 14:45 UTC → 2026-11-18 14:44 UTC)

The dev window fell 2.80% ($65,083 → $63,261); buy-and-hold lost about
$30.60 after costs. The bot was tested with a local replay implementing the
harness's exact integer fill model (fee, slippage, constant-product impact
against each bar's open depth, fills at the next bar's open, final flatten
at the last close), run twice to check determinism.

| Segment | Net PnL | Trades | Max drawdown |
|---|---|---|---|
| Train, first 18 h | +$8.64 | 7 | 0.65% |
| Test, last 6 h (−2.17%) | $0.00 | 0 | 0.00% |
| Full dev window | **+$8.64** | **7** | **0.65%** |

The profit came from one trade that caught the window's one big climb
(buy $63,921 → add $64,431 → sell $65,062), minus two half-size false
entries in choppy hours (−$1.95 and −$2.03). In the last 6 hours, a steady
decline, the bot stayed in cash the whole time and lost nothing. The tuning
used the first 18 hours; the last 6 hours were held out and only verified.

## Files

- `main.py` — the bot (Python 3.13, standard library only).
- `vendor/makefun_bars.py` — the kit's protocol shim, copied unchanged.
- `NOTES.md` — dev-window analysis and design notes.
- `LICENSE` — MIT.

## Run it

The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout. Grade it locally
with the kit (needs Docker):

```
node cli/makefun.mjs grade-local --kit <kit> --bot . --driver docker
```
