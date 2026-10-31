import math
from typing import List, Dict, Any, Optional, Tuple
from .data_validator import MarketDataValidator

# =========================================================================
# 1. TECHNICAL INDICATORS COMPUTATION ENGINE
# =========================================================================

def compute_sma(prices: List[float], period: int) -> List[Optional[float]]:
    res = [None] * len(prices)
    if len(prices) < period:
        return res
    running_sum = sum(prices[:period])
    res[period - 1] = running_sum / period
    for i in range(period, len(prices)):
        running_sum += prices[i] - prices[i - period]
        res[i] = running_sum / period
    return res

def compute_ema(prices: List[float], period: int) -> List[Optional[float]]:
    res = [None] * len(prices)
    if len(prices) < period:
        return res
    multiplier = 2.0 / (period + 1.0)
    sma_init = sum(prices[:period]) / period
    res[period - 1] = sma_init
    prev = sma_init
    for i in range(period, len(prices)):
        curr = (prices[i] - prev) * multiplier + prev
        res[i] = curr
        prev = curr
    return res

def compute_rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
    res = [None] * len(prices)
    if len(prices) <= period:
        return res
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = prices[i] - prices[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        res[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        res[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gain = max(0.0, diff)
        loss = max(0.0, -diff)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            res[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            res[i] = round(100.0 - (100.0 / (1.0 + rs)), 2)
    return res

def compute_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[Optional[float]]]:
    fast_ema = compute_ema(prices, fast)
    slow_ema = compute_ema(prices, slow)
    macd_line = [None] * len(prices)
    valid_macd_vals = []
    valid_indices = []

    for i in range(len(prices)):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            val = fast_ema[i] - slow_ema[i]
            macd_line[i] = val
            valid_macd_vals.append(val)
            valid_indices.append(i)

    signal_line = [None] * len(prices)
    if len(valid_macd_vals) >= signal:
        sig_ema = compute_ema(valid_macd_vals, signal)
        for idx_sig, val_sig in enumerate(sig_ema):
            orig_idx = valid_indices[idx_sig]
            signal_line[orig_idx] = val_sig

    hist = [None] * len(prices)
    for i in range(len(prices)):
        if macd_line[i] is not None and signal_line[i] is not None:
            hist[i] = round(macd_line[i] - signal_line[i], 2)

    return {"macd": macd_line, "signal": signal_line, "histogram": hist}

def compute_bollinger_bands(prices: List[float], period: int = 20, std_mult: float = 2.0) -> Dict[str, List[Optional[float]]]:
    sma = compute_sma(prices, period)
    upper = [None] * len(prices)
    lower = [None] * len(prices)
    bandwidth = [None] * len(prices)

    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1 : i + 1]
        mean = sma[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std_dev = math.sqrt(variance)
        upper[i] = round(mean + (std_mult * std_dev), 2)
        lower[i] = round(mean - (std_mult * std_dev), 2)
        if mean > 0:
            bandwidth[i] = round(((upper[i] - lower[i]) / mean) * 100, 2)

    return {"middle": sma, "upper": upper, "lower": lower, "bandwidth": bandwidth}

# =========================================================================
# 2. SMART MONEY CONCEPTS (SMC): FVG & ORDER BLOCKS
# =========================================================================

def detect_smc_structures(candles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Identifies Fair Value Gaps (FVG) and Order Blocks (OB) across candles.
    """
    fvgs = []
    order_blocks = []
    n = len(candles)
    if n < 3:
        return {"fvgs": fvgs, "order_blocks": order_blocks}

    for i in range(2, n):
        c0 = candles[i - 2]
        c1 = candles[i - 1]
        c2 = candles[i]

        # 1. Bullish FVG: Low of candle 2 is higher than High of candle 0
        if c2["low"] > c0["high"]:
            gap_size = round(c2["low"] - c0["high"], 2)
            gap_pct = round((gap_size / c1["close"]) * 100, 2)
            if gap_pct >= 0.15:  # meaningful imbalance
                fvgs.append({
                    "type": "BULLISH_FVG",
                    "bar_index": i - 1,
                    "time": c1["time"],
                    "top": c2["low"],
                    "bottom": c0["high"],
                    "gap_size": gap_size,
                    "mitigated": False
                })

        # 2. Bearish FVG: High of candle 2 is lower than Low of candle 0
        elif c2["high"] < c0["low"]:
            gap_size = round(c0["low"] - c2["high"], 2)
            gap_pct = round((gap_size / c1["close"]) * 100, 2)
            if gap_pct >= 0.15:
                fvgs.append({
                    "type": "BEARISH_FVG",
                    "bar_index": i - 1,
                    "time": c1["time"],
                    "top": c0["low"],
                    "bottom": c2["high"],
                    "gap_size": gap_size,
                    "mitigated": False
                })

        # 3. Order Block Detection: Last down candle before an energetic rally
        if i >= 4:
            # Bullish OB
            if c1["close"] > c1["open"] and (c1["close"] - c1["open"]) > 2 * abs(c0["close"] - c0["open"]):
                if c0["close"] < c0["open"]:  # Bearish candle prior to pump
                    order_blocks.append({
                        "type": "BULLISH_OB",
                        "bar_index": i - 2,
                        "time": c0["time"],
                        "high": c0["high"],
                        "low": c0["low"],
                        "mitigated": False
                    })
            # Bearish OB
            elif c1["close"] < c1["open"] and (c1["open"] - c1["close"]) > 2 * abs(c0["close"] - c0["open"]):
                if c0["close"] > c0["open"]:  # Bullish candle prior to dump
                    order_blocks.append({
                        "type": "BEARISH_OB",
                        "bar_index": i - 2,
                        "time": c0["time"],
                        "high": c0["high"],
                        "low": c0["low"],
                        "mitigated": False
                    })

    return {"fvgs": fvgs, "order_blocks": order_blocks}

# =========================================================================
# 3. BACKTESTING ENGINE
# =========================================================================

class StrategyLabBacktester:
    """
    Simulates quantitative trading strategies with realistic fees, slippage,
    and out-of-sample walk-forward split validation.
    """
    AVAILABLE_STRATEGIES = [
        "sma_ema_crossover",
        "rsi_mean_reversion",
        "macd_momentum",
        "bollinger_breakout",
        "smc_fair_value_gap"
    ]

    @classmethod
    def run_backtest(
        cls,
        candles: List[Dict[str, Any]],
        strategy_name: str = "sma_ema_crossover",
        params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 1000000.0,
        slippage_pct: float = 0.05,
        fee_pct: float = 0.03,
        walk_forward_ratio: float = 0.70
    ) -> Dict[str, Any]:
        """
        Executes backtest with walk-forward split, computing Win Rate %,
        Profit Factor, Max Drawdown %, Equity Curve, and Trade Logs.
        """
        val_res = MarketDataValidator.validate_candles(candles, data_source_label="BACKTEST_INPUT")
        if not val_res["is_valid"]:
            return {"success": False, "error": "Invalid candlestick dataset", "details": val_res["errors"]}

        clean_candles = val_res["clean_candles"]
        total_bars = len(clean_candles)
        if total_bars < 30:
            return {"success": False, "error": "Insufficient candles for backtesting (minimum 30 required)."}

        params = params or {}
        split_idx = int(total_bars * walk_forward_ratio)
        in_sample_candles = clean_candles[:split_idx]
        out_of_sample_candles = clean_candles[split_idx:]

        # Run complete run
        full_res = cls._simulate_strategy(clean_candles, strategy_name, params, initial_capital, slippage_pct, fee_pct)
        in_sample_res = cls._simulate_strategy(in_sample_candles, strategy_name, params, initial_capital, slippage_pct, fee_pct)
        out_sample_res = cls._simulate_strategy(out_of_sample_candles, strategy_name, params, initial_capital, slippage_pct, fee_pct)

        return {
            "success": True,
            "disclaimer": "Educational & Simulated Analytical Backtest Only — Not Financial Advice",
            "strategy": strategy_name,
            "parameters": params,
            "candle_count": total_bars,
            "full_period": {
                "initial_capital": initial_capital,
                "final_equity": full_res["final_equity"],
                "total_return_amount": full_res["total_return_amount"],
                "total_return_pct": full_res["total_return_pct"],
                "win_rate_pct": full_res["win_rate_pct"],
                "profit_factor": full_res["profit_factor"],
                "max_drawdown_amount": full_res["max_drawdown_amount"],
                "max_drawdown_pct": full_res["max_drawdown_pct"],
                "total_trades": full_res["total_trades"],
                "winning_trades": full_res["winning_trades"],
                "losing_trades": full_res["losing_trades"],
                "sharpe_ratio": full_res["sharpe_ratio"],
                "trades": full_res["trades"][:50],  # Latest 50 trades
                "equity_curve": full_res["equity_curve"]
            },
            "walk_forward_validation": {
                "in_sample_win_rate_pct": in_sample_res["win_rate_pct"],
                "in_sample_return_pct": in_sample_res["total_return_pct"],
                "in_sample_profit_factor": in_sample_res["profit_factor"],
                "out_of_sample_win_rate_pct": out_sample_res["win_rate_pct"],
                "out_of_sample_return_pct": out_sample_res["total_return_pct"],
                "out_of_sample_profit_factor": out_sample_res["profit_factor"],
                "is_robust": (out_sample_res["profit_factor"] >= 1.05 and out_sample_res["win_rate_pct"] >= 45.0)
            }
        }

    @classmethod
    def _simulate_strategy(
        cls,
        candles: List[Dict[str, Any]],
        strategy_name: str,
        params: Dict[str, Any],
        initial_capital: float,
        slippage_pct: float,
        fee_pct: float
    ) -> Dict[str, Any]:
        closes = [c["close"] for c in candles]
        signals = [0] * len(candles)  # 1 = BUY, -1 = SELL / EXIT

        # -------------------------------------------------------------
        # Generate Signals
        # -------------------------------------------------------------
        if strategy_name == "sma_ema_crossover":
            fast_p = int(params.get("fast_period", 9))
            slow_p = int(params.get("slow_period", 21))
            fast_ema = compute_ema(closes, fast_p)
            slow_ema = compute_ema(closes, slow_p)
            for i in range(1, len(candles)):
                if fast_ema[i] and slow_ema[i] and fast_ema[i-1] and slow_ema[i-1]:
                    if fast_ema[i-1] <= slow_ema[i-1] and fast_ema[i] > slow_ema[i]:
                        signals[i] = 1  # Golden cross
                    elif fast_ema[i-1] >= slow_ema[i-1] and fast_ema[i] < slow_ema[i]:
                        signals[i] = -1 # Death cross

        elif strategy_name == "rsi_mean_reversion":
            period = int(params.get("period", 14))
            oversold = float(params.get("oversold", 30.0))
            overbought = float(params.get("overbought", 70.0))
            rsi = compute_rsi(closes, period)
            for i in range(1, len(candles)):
                if rsi[i] and rsi[i-1]:
                    if rsi[i-1] < oversold and rsi[i] >= oversold:
                        signals[i] = 1
                    elif rsi[i-1] > overbought and rsi[i] <= overbought:
                        signals[i] = -1

        elif strategy_name == "macd_momentum":
            fast = int(params.get("fast", 12))
            slow = int(params.get("slow", 26))
            sig = int(params.get("signal", 9))
            macd_dict = compute_macd(closes, fast, slow, sig)
            hist = macd_dict["histogram"]
            for i in range(1, len(candles)):
                if hist[i] is not None and hist[i-1] is not None:
                    if hist[i-1] <= 0 and hist[i] > 0:
                        signals[i] = 1
                    elif hist[i-1] >= 0 and hist[i] < 0:
                        signals[i] = -1

        elif strategy_name == "bollinger_breakout":
            bb = compute_bollinger_bands(closes, int(params.get("period", 20)))
            upper = bb["upper"]
            lower = bb["lower"]
            for i in range(1, len(candles)):
                if upper[i] and lower[i]:
                    if closes[i-1] <= upper[i-1] and closes[i] > upper[i]:
                        signals[i] = 1
                    elif closes[i-1] >= lower[i-1] and closes[i] < lower[i]:
                        signals[i] = -1

        elif strategy_name == "smc_fair_value_gap":
            smc = detect_smc_structures(candles)
            fvgs = smc["fvgs"]
            for f in fvgs:
                b_idx = f["bar_index"]
                if b_idx < len(signals):
                    signals[b_idx] = 1 if f["type"] == "BULLISH_FVG" else -1

        # -------------------------------------------------------------
        # Execute Trades Simulation
        # -------------------------------------------------------------
        equity = initial_capital
        peak_equity = initial_capital
        max_drawdown = 0.0
        position = None  # {entry_price, entry_time, qty}
        trades = []
        equity_curve = []

        total_friction = (slippage_pct + fee_pct) / 100.0

        for i, c in enumerate(candles):
            price = c["close"]
            sig = signals[i]
            t = c["time"]

            # Exit check if currently in position
            if position:
                # Check exit signal or force close at last bar
                should_exit = (sig == -1) or (i == len(candles) - 1)
                if should_exit:
                    exit_price = price * (1.0 - total_friction)
                    pnl = (exit_price - position["entry_price"]) * position["qty"]
                    ret_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * 100.0
                    equity += pnl

                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": t,
                        "entry_price": round(position["entry_price"], 2),
                        "exit_price": round(exit_price, 2),
                        "qty": position["qty"],
                        "pnl": round(pnl, 2),
                        "return_pct": round(ret_pct, 2),
                        "reason": "SIGNAL_EXIT" if sig == -1 else "END_OF_DATA"
                    })
                    position = None

            # Entry check
            elif sig == 1 and not position:
                entry_price = price * (1.0 + total_friction)
                # Allocate 95% of available equity per trade
                allocated = equity * 0.95
                qty = max(1, int(allocated / entry_price))
                if qty * entry_price <= equity:
                    position = {
                        "entry_price": entry_price,
                        "entry_time": t,
                        "qty": qty
                    }

            # Update curve & drawdown
            curr_equity = equity
            if position:
                unrealized = (price - position["entry_price"]) * position["qty"]
                curr_equity += unrealized

            if curr_equity > peak_equity:
                peak_equity = curr_equity
            dd = peak_equity - curr_equity
            if dd > max_drawdown:
                max_drawdown = dd

            equity_curve.append({
                "time": t,
                "equity": round(curr_equity, 2),
                "drawdown": round(dd, 2)
            })

        # Calculate summary statistics
        total_trades = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = round((len(wins) / total_trades * 100.0), 2) if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        total_ret_amt = round(equity - initial_capital, 2)
        total_ret_pct = round(((equity - initial_capital) / initial_capital) * 100.0, 2)
        max_dd_pct = round((max_drawdown / peak_equity * 100.0), 2) if peak_equity > 0 else 0.0

        # Simple Sharpe calculation from trade return percentages
        if total_trades > 1:
            rets = [t["return_pct"] for t in trades]
            mean_ret = sum(rets) / len(rets)
            var_ret = sum((r - mean_ret) ** 2 for r in rets) / (len(rets) - 1)
            std_ret = math.sqrt(var_ret) if var_ret > 0 else 1.0
            sharpe = round((mean_ret / std_ret) * math.sqrt(total_trades), 2)
        else:
            sharpe = 0.0

        return {
            "final_equity": round(equity, 2),
            "total_return_amount": total_ret_amt,
            "total_return_pct": total_ret_pct,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_amount": round(max_drawdown, 2),
            "max_drawdown_pct": max_dd_pct,
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "sharpe_ratio": sharpe,
            "trades": trades,
            "equity_curve": equity_curve
        }
