import pytest
from backend.trading.data_validator import MarketDataValidator
from backend.trading.strategy_lab import (
    compute_sma,
    compute_ema,
    compute_rsi,
    compute_macd,
    compute_bollinger_bands,
    detect_smc_structures,
    StrategyLabBacktester
)
from backend.trading.paper_portfolio import PaperTradingPortfolio
from backend.trading.trading_psychology import TradingPsychologyEngine

def generate_sample_candles(count: int = 60) -> list:
    candles = []
    base_price = 24000.0
    for i in range(count):
        # Create an oscillating price wave
        delta = (i % 10 - 5) * 15.0
        c = base_price + delta
        o = c - 5.0
        h = max(o, c) + 10.0
        l = min(o, c) - 10.0
        candles.append({
            "time": 1700000000 + (i * 900),
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 1000 + i * 10
        })
    return candles

def test_data_validator():
    candles = generate_sample_candles(10)
    res = MarketDataValidator.validate_candles(candles, "TEST")
    assert res["is_valid"] is True
    assert res["candle_count"] == 10

    # Invalidate one candle (High lower than Open)
    bad_candles = [dict(c) for c in candles]
    bad_candles[3]["high"] = bad_candles[3]["open"] - 20.0
    bad_res = MarketDataValidator.validate_candles(bad_candles, "TEST")
    assert bad_res["is_valid"] is False
    assert bad_res["error_count"] > 0

def test_technical_indicators():
    prices = [100.0 + i * 2.0 for i in range(35)]
    sma = compute_sma(prices, 10)
    assert sma[9] is not None
    assert sma[0] is None

    ema = compute_ema(prices, 10)
    assert ema[9] is not None

    rsi = compute_rsi(prices, 14)
    assert rsi[14] is not None

    macd = compute_macd(prices)
    assert "macd" in macd and "signal" in macd and "histogram" in macd

    bb = compute_bollinger_bands(prices, 20)
    assert bb["upper"][19] is not None
    assert bb["lower"][19] is not None
    assert bb["upper"][19] > bb["lower"][19]

def test_smc_structures():
    candles = [
        {"time": 1, "open": 100, "high": 105, "low": 95, "close": 102, "volume": 100},
        {"time": 2, "open": 102, "high": 120, "low": 101, "close": 118, "volume": 500},
        {"time": 3, "open": 118, "high": 130, "low": 115, "close": 128, "volume": 300},
    ]
    # Candle 3 Low (115) > Candle 1 High (105) -> Bullish FVG
    smc = detect_smc_structures(candles)
    assert len(smc["fvgs"]) > 0
    assert smc["fvgs"][0]["type"] == "BULLISH_FVG"

def test_backtest_execution():
    candles = generate_sample_candles(50)
    res = StrategyLabBacktester.run_backtest(
        candles=candles,
        strategy_name="sma_ema_crossover",
        params={"fast_period": 5, "slow_period": 15},
        initial_capital=1000000.0
    )
    assert res["success"] is True
    assert "full_period" in res
    assert "win_rate_pct" in res["full_period"]
    assert "profit_factor" in res["full_period"]
    assert "walk_forward_validation" in res

def test_paper_portfolio_lifecycle():
    # Reset account
    PaperTradingPortfolio.reset_account(initial_capital=1000000.0)
    summary = PaperTradingPortfolio.get_portfolio_summary()
    assert summary["cash_balance"] == 1000000.0
    assert len(summary["positions"]) == 0

    # Execute BUY order
    buy_res = PaperTradingPortfolio.execute_order("NIFTY50", "BUY", 10, price=24000.0)
    assert buy_res["success"] is True
    assert buy_res["status"] == "FILLED"

    summary_after_buy = PaperTradingPortfolio.get_portfolio_summary()
    assert summary_after_buy["cash_balance"] < 1000000.0
    assert len(summary_after_buy["positions"]) == 1

    # Execute SELL order
    sell_res = PaperTradingPortfolio.execute_order("NIFTY50", "SELL", 10, price=24200.0)
    assert sell_res["success"] is True
    assert sell_res["status"] == "FILLED"

    summary_after_sell = PaperTradingPortfolio.get_portfolio_summary()
    assert len(summary_after_sell["positions"]) == 0

def test_trading_psychology_engine():
    # Disciplined trade with all checks
    entry = TradingPsychologyEngine.record_entry(
        symbol="NIFTY50",
        action="BUY",
        emotion_tag="Disciplined",
        checklist_answers=[True, True, True, True],
        notes="Clean 15M breaker block bounce."
    )
    assert entry["success"] is True
    assert entry["discipline_score"] >= 80

    # FOMO trade with missed checklist
    fomo_entry = TradingPsychologyEngine.record_entry(
        symbol="BANKNIFTY",
        action="BUY",
        emotion_tag="FOMO",
        checklist_answers=[False, False, True, False],
        notes="Chased green candle."
    )
    assert fomo_entry["discipline_score"] < 60

    analytics = TradingPsychologyEngine.get_psychology_analytics()
    assert analytics["total_entries"] >= 2

