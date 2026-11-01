"""
Execution script for data_analyst skill.
Performs statistical and financial analytics on numerical series.
"""

import sys
import json
import math

def analyze_series(series: list, risk_free_rate: float = 0.05):
    if not series:
        return {"status": "ERROR", "error": "Empty series provided."}

    # Extract numerical values
    vals = []
    for item in series:
        if isinstance(item, (int, float)):
            vals.append(float(item))
        elif isinstance(item, dict):
            v = item.get("value") or item.get("price") or item.get("close")
            if v is not None:
                vals.append(float(v))

    if not vals:
        return {"status": "ERROR", "error": "No valid numerical values found in series."}

    n = len(vals)
    mean_val = sum(vals) / n
    variance = sum((x - mean_val) ** 2 for x in vals) / (n - 1 if n > 1 else 1)
    std_dev = math.sqrt(variance)

    # Max Drawdown calculation
    peak = vals[0]
    max_dd = 0.0
    for v in vals:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Simple Sharpe estimate
    annualized_return = ((vals[-1] - vals[0]) / vals[0]) if vals[0] != 0 else 0
    sharpe = round((annualized_return - risk_free_rate) / (std_dev if std_dev > 0 else 1.0), 2)

    table_data = [
        {"Metric": "Observations", "Value": str(n)},
        {"Metric": "Mean Value", "Value": str(round(mean_val, 2))},
        {"Metric": "Std Dev", "Value": str(round(std_dev, 2))},
        {"Metric": "Min Value", "Value": str(round(min(vals), 2))},
        {"Metric": "Max Value", "Value": str(round(max(vals), 2))},
        {"Metric": "Max Drawdown", "Value": f"{round(max_dd * 100, 2)}%"},
        {"Metric": "Estimated Sharpe", "Value": str(sharpe)}
    ]

    return {
        "status": "SUCCESS",
        "count": n,
        "mean": round(mean_val, 2),
        "std_dev": round(std_dev, 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "max_drawdown": round(max_dd, 4),
        "sharpe_ratio": sharpe,
        "table_data": table_data,
        "summary": f"Dataset of {n} samples analyzed. Mean: {round(mean_val, 2)}, Volatility: {round(std_dev, 2)}, Max Drawdown: {round(max_dd * 100, 2)}%."
    }

def main():
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
    except Exception:
        params = {}

    series = params.get("series") or [100.0, 102.5, 101.8, 105.0, 104.2, 108.5, 107.0, 112.0, 110.5, 115.0]
    rf = float(params.get("risk_free_rate", 0.05))

    res = analyze_series(series, rf)
    print(json.dumps(res, ensure_ascii=False))

if __name__ == "__main__":
    main()

