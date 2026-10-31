import time
import uuid
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import settings
from ..security import log_audit_event

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"

def init_paper_trading_db():
    """Initializes tables for simulated paper portfolio, orders, and trade executions."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        # Portfolio balance state
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_account (
                id INTEGER PRIMARY KEY,
                currency TEXT DEFAULT 'INR',
                initial_capital REAL DEFAULT 1000000.0,
                cash_balance REAL DEFAULT 1000000.0,
                updated_at REAL
            );
        """)
        # Initialize default record if empty
        cursor.execute("SELECT COUNT(*) FROM paper_account;")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO paper_account (id, currency, initial_capital, cash_balance, updated_at) VALUES (1, 'INR', 1000000.0, 1000000.0, ?);",
                (time.time(),)
            )

        # Open positions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                position_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL, -- LONG or SHORT
                quantity INTEGER NOT NULL,
                avg_entry_price REAL NOT NULL,
                current_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                unrealized_pnl REAL DEFAULT 0.0,
                created_at REAL,
                updated_at REAL
            );
        """)

        # Order history and execution audit
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_orders (
                order_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                order_type TEXT NOT NULL, -- MARKET, LIMIT, SL
                side TEXT NOT NULL, -- BUY, SELL
                quantity INTEGER NOT NULL,
                requested_price REAL,
                executed_price REAL,
                status TEXT NOT NULL, -- FILLED, PENDING, CANCELLED, REJECTED
                pnl REAL DEFAULT 0.0,
                created_at REAL,
                filled_at REAL
            );
        """)
        conn.commit()

init_paper_trading_db()

class PaperTradingPortfolio:
    """
    Simulated Paper-Trading Portfolio Manager.
    Strictly educational and non-real-money simulation.
    """
    @classmethod
    def get_portfolio_summary(cls, live_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        live_prices = live_prices or {}
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_account WHERE id = 1;")
            acc = dict(cursor.fetchone() or {"cash_balance": 1000000.0, "initial_capital": 1000000.0, "currency": "INR"})

            cursor.execute("SELECT * FROM paper_positions;")
            positions_rows = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT * FROM paper_orders ORDER BY created_at DESC LIMIT 50;")
            recent_orders = [dict(r) for r in cursor.fetchall()]

        # Compute positions unrealized PnL
        positions = []
        total_unrealized_pnl = 0.0
        invested_value = 0.0

        for pos in positions_rows:
            sym = pos["symbol"]
            curr_price = live_prices.get(sym, pos["current_price"])
            side = pos["side"]
            qty = pos["quantity"]
            entry = pos["avg_entry_price"]

            if side == "LONG":
                unrealized = (curr_price - entry) * qty
            else:
                unrealized = (entry - curr_price) * qty

            pos["current_price"] = curr_price
            pos["unrealized_pnl"] = round(unrealized, 2)
            pos["pnl_pct"] = round((unrealized / (entry * qty)) * 100.0, 2) if entry * qty > 0 else 0.0
            total_unrealized_pnl += unrealized
            invested_value += curr_price * qty
            positions.append(pos)

        cash = acc["cash_balance"]
        total_equity = cash + invested_value
        initial = acc["initial_capital"]
        total_pnl = total_equity - initial
        total_pnl_pct = round((total_pnl / initial) * 100.0, 2) if initial > 0 else 0.0

        return {
            "disclaimer": "Educational & Simulated Paper Trading Only — Not Real Financial Brokerage Orders",
            "currency": acc.get("currency", "INR"),
            "initial_capital": round(initial, 2),
            "cash_balance": round(cash, 2),
            "invested_value": round(invested_value, 2),
            "total_portfolio_equity": round(total_equity, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": total_pnl_pct,
            "open_positions_count": len(positions),
            "positions": positions,
            "recent_orders": recent_orders
        }

    @classmethod
    def execute_order(
        cls,
        symbol: str,
        side: str,  # BUY or SELL
        quantity: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Executes a simulated order with spread and slippage estimation.
        """
        if quantity <= 0:
            return {"success": False, "error": "Order quantity must be positive."}

        side = side.upper()
        if side not in ["BUY", "SELL"]:
            return {"success": False, "error": "Order side must be BUY or SELL."}

        order_id = f"ord_{uuid.uuid4().hex[:10]}"
        now = time.time()

        # Simulated price with 0.05% realistic slippage
        exec_price = price if price and price > 0 else 100.0
        slippage_mult = 1.0005 if side == "BUY" else 0.9995
        executed_price = round(exec_price * slippage_mult, 2)
        order_cost = executed_price * quantity

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT cash_balance FROM paper_account WHERE id = 1;")
            row = cursor.fetchone()
            cash = row["cash_balance"] if row else 1000000.0

            if side == "BUY":
                if cash < order_cost:
                    return {"success": False, "error": f"Insufficient simulated cash (Available: ₹{cash:.2f}, Required: ₹{order_cost:.2f})"}

                # Deduct cash
                new_cash = cash - order_cost
                cursor.execute("UPDATE paper_account SET cash_balance = ?, updated_at = ? WHERE id = 1;", (new_cash, now))

                # Create or update position
                cursor.execute("SELECT * FROM paper_positions WHERE symbol = ? AND side = 'LONG';", (symbol,))
                existing_pos = cursor.fetchone()
                if existing_pos:
                    old_qty = existing_pos["quantity"]
                    old_entry = existing_pos["avg_entry_price"]
                    new_qty = old_qty + quantity
                    new_avg = round(((old_qty * old_entry) + (quantity * executed_price)) / new_qty, 2)
                    cursor.execute("""
                        UPDATE paper_positions
                        SET quantity = ?, avg_entry_price = ?, current_price = ?, stop_loss = ?, take_profit = ?, updated_at = ?
                        WHERE position_id = ?;
                    """, (new_qty, new_avg, executed_price, stop_loss, take_profit, now, existing_pos["position_id"]))
                else:
                    pos_id = f"pos_{uuid.uuid4().hex[:10]}"
                    cursor.execute("""
                        INSERT INTO paper_positions (position_id, symbol, side, quantity, avg_entry_price, current_price, stop_loss, take_profit, created_at, updated_at)
                        VALUES (?, ?, 'LONG', ?, ?, ?, ?, ?, ?, ?);
                    """, (pos_id, symbol, quantity, executed_price, executed_price, stop_loss, take_profit, now, now))

                # Log order
                cursor.execute("""
                    INSERT INTO paper_orders (order_id, symbol, order_type, side, quantity, requested_price, executed_price, status, pnl, created_at, filled_at)
                    VALUES (?, ?, ?, 'BUY', ?, ?, ?, 'FILLED', 0.0, ?, ?);
                """, (order_id, symbol, order_type, quantity, price, executed_price, now, now))

            elif side == "SELL":
                # Check existing long position to close
                cursor.execute("SELECT * FROM paper_positions WHERE symbol = ? AND side = 'LONG';", (symbol,))
                existing_pos = cursor.fetchone()
                if not existing_pos or existing_pos["quantity"] < quantity:
                    avail = existing_pos["quantity"] if existing_pos else 0
                    return {"success": False, "error": f"Cannot sell {quantity} shares of {symbol}; only {avail} held."}

                old_qty = existing_pos["quantity"]
                entry_price = existing_pos["avg_entry_price"]
                realized_pnl = round((executed_price - entry_price) * quantity, 2)
                sale_proceeds = executed_price * quantity
                new_cash = cash + sale_proceeds
                cursor.execute("UPDATE paper_account SET cash_balance = ?, updated_at = ? WHERE id = 1;", (new_cash, now))

                if old_qty == quantity:
                    cursor.execute("DELETE FROM paper_positions WHERE position_id = ?;", (existing_pos["position_id"],))
                else:
                    cursor.execute("""
                        UPDATE paper_positions SET quantity = ?, current_price = ?, updated_at = ? WHERE position_id = ?;
                    """, (old_qty - quantity, executed_price, now, existing_pos["position_id"]))

                # Log order with realized P&L
                cursor.execute("""
                    INSERT INTO paper_orders (order_id, symbol, order_type, side, quantity, requested_price, executed_price, status, pnl, created_at, filled_at)
                    VALUES (?, ?, ?, 'SELL', ?, ?, ?, 'FILLED', ?, ?, ?);
                """, (order_id, symbol, order_type, quantity, price, executed_price, realized_pnl, now, now))

            conn.commit()

        log_audit_event("paper_trade_order", f"{side} {quantity} {symbol} @ {executed_price}", "safe", "success")
        return {
            "success": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "executed_price": executed_price,
            "status": "FILLED",
            "message": f"सिम्युलेटेड पेपर ऑर्डर निष्पादित: {side} {quantity} {symbol} @ ₹{executed_price}"
        }

    @classmethod
    def reset_account(cls, initial_capital: float = 1000000.0) -> Dict[str, Any]:
        """Resets the paper trading account to default starting balance."""
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE paper_account SET initial_capital = ?, cash_balance = ?, updated_at = ? WHERE id = 1;", (initial_capital, initial_capital, time.time()))
            cursor.execute("DELETE FROM paper_positions;")
            cursor.execute("DELETE FROM paper_orders;")
            conn.commit()
        log_audit_event("reset_paper_account", f"Capital: {initial_capital}", "high", "success")
        return {"success": True, "message": f"पेपर ट्रेडिंग अकाउंट ₹{initial_capital:,.2f} पर रीसेट कर दिया गया है।"}

