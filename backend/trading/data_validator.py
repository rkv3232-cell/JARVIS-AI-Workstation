import time
from typing import List, Dict, Any, Tuple

class MarketDataValidator:
    """
    Validates the integrity, chronology, and price logic of candlestick data
    before execution in the Strategy Lab or Paper Trading Engine.
    """
    @staticmethod
    def validate_candles(candles: List[Dict[str, Any]], data_source_label: str = "HISTORICAL") -> Dict[str, Any]:
        """
        Runs rigorous mathematical and structural integrity checks on OHLCV candles.
        Returns validation summary, error list, and cleaned candle list.
        """
        if not candles:
            return {
                "is_valid": False,
                "data_source": data_source_label,
                "error_count": 1,
                "errors": ["Candle list is completely empty."],
                "clean_candles": []
            }

        errors = []
        warnings = []
        clean_candles = []
        seen_timestamps = set()
        prev_time = None

        for idx, c in enumerate(candles):
            # 1. Structure check
            req_keys = ["open", "high", "low", "close"]
            if not all(k in c for k in req_keys):
                errors.append(f"Candle at index {idx} missing required OHLC keys: {c}")
                continue

            try:
                o = float(c["open"])
                h = float(c["high"])
                l = float(c["low"])
                cl = float(c["close"])
                vol = float(c.get("volume", 0.0))
                ts = c.get("time") or c.get("timestamp") or (idx * 60)
            except (ValueError, TypeError) as err:
                errors.append(f"Non-numeric value in candle {idx}: {err}")
                continue

            # 2. Mathematical OHLC consistency
            if h < max(o, cl):
                errors.append(f"Bar {idx}: High ({h}) cannot be lower than Open ({o}) or Close ({cl}).")
            if l > min(o, cl):
                errors.append(f"Bar {idx}: Low ({l}) cannot be higher than Open ({o}) or Close ({cl}).")
            if vol < 0:
                warnings.append(f"Bar {idx}: Volume ({vol}) is negative; normalized to 0.")
                vol = 0.0

            # 3. Timestamp chronology & duplicates
            if ts in seen_timestamps:
                warnings.append(f"Bar {idx}: Duplicate timestamp detected ({ts}); skipping duplicate.")
                continue
            seen_timestamps.add(ts)

            if prev_time is not None and isinstance(ts, (int, float)) and isinstance(prev_time, (int, float)):
                if ts < prev_time:
                    warnings.append(f"Bar {idx}: Timestamp out of chronological order ({ts} < {prev_time}).")

            prev_time = ts
            clean_candles.append({
                "time": ts,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(cl, 2),
                "volume": round(vol, 2)
            })

        # 4. Check for stale quote (more than 24 hours behind current wall clock for live data)
        is_stale = False
        if clean_candles and data_source_label.upper().startswith("LIVE"):
            last_ts = clean_candles[-1]["time"]
            if isinstance(last_ts, (int, float)) and (time.time() - last_ts > 86400):
                is_stale = True
                warnings.append("Latest quote appears stale (>24 hours lag).")

        return {
            "is_valid": len(errors) == 0 and len(clean_candles) > 0,
            "data_source": data_source_label,
            "candle_count": len(clean_candles),
            "is_stale": is_stale,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors[:20],
            "warnings": warnings[:20],
            "clean_candles": clean_candles
        }
