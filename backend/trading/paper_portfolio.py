import time
import uuid
import json
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import settings
from ..security import log_audit_event

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"
_portfolio_lock = threading.Lock()

# Standard Trading Frictions
SLIPPAGE_RATE = 0.0005      # 0.05% slippage on simulated execution
SPREAD_RATE = 0.0002        # 0.02% spread
COMMISSION_FLAT = 20.0      # ₹20 flat brokerage per executed trade

SUPPORTED_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_LOSS"}

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
                order_type TEXT NOT NULL, -- MARKET, LIMIT, STOP_LOSS
                side TEXT NOT NULL, -- BUY, SELL
                quantity INTEGER NOT NULL,
                requested_price REAL,
                executed_price REAL,
                fee REAL DEFAULT 0.0,
                status TEXT NOT NULL, -- FILLED, PENDING, CANCELLED, REJECTED
                pnl REAL DEFAULT 0.0,
                notes TEXT,
                created_at REAL,
                filled_at REAL
            );
        """)

        # Backup snapshots for reversible reset
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_account_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                initial_capital REAL NOT NULL,
                cash_balance REAL NOT NULL,
                positions_json TEXT NOT NULL,
                orders_json TEXT NOT NULL
            );
        """)

        # Auto-migration for paper_orders schema updates
        cursor.execute("PRAGMA table_info(paper_orders);")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if "fee" not in existing_cols:
            try:
                cursor.execute("ALTER TABLE paper_orders ADD COLUMN fee REAL DEFAULT 0.0;")
            except Exception:
                pass
        if "notes" not in existing_cols:
            try:
                cursor.execute("ALTER TABLE paper_orders ADD COLUMN notes TEXT;")
            except Exception:
                pass

        conn.commit()

init_paper_trading_db()

class PaperTradingPortfolio:
    """
    Simulated Paper-Trading Portfolio Manager.
    Strictly educational and non-real-money simulation.
    Enforces pending limit/stop queues, tick-driven fills, and reversible resets.
    """
    @classmethod
    def get_portfolio_summary(cls, live_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        live_prices = live_prices or {}
        # Evaluate pending orders and TP/SL triggers against active live ticks
        if live_prices:
            for s, p in live_prices.items():
                if isinstance(p, (int, float)) and p > 0:
                    cls.evaluate_pending_orders_and_triggers(s, float(p))

        with _portfolio_lock, sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_account WHERE id = 1;")
            acc = dict(cursor.fetchone() or {"cash_balance": 1000000.0, "initial_capital": 1000000.0, "currency": "INR"})

            cursor.execute("SELECT * FROM paper_positions;")
            positions_rows = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT * FROM paper_orders ORDER BY created_at DESC LIMIT 50;")
            recent_orders = [dict(r) for r in cursor.fetchall()]

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
        Submits a simulated paper order.
        Validates order types, rejects missing prices for market execution,
        queues pending limit/stop orders, and applies commissions and slippage.
        """
        if quantity <= 0:
            return {"success": False, "error": "Order quantity must be positive."}

        side = side.upper().strip()
        if side not in ["BUY", "SELL"]:
            return {"success": False, "error": "Order side must be BUY or SELL."}

        order_type = order_type.upper().strip()
        if order_type not in SUPPORTED_ORDER_TYPES:
            return {"success": False, "error": f"Unsupported order type '{order_type}'. Allowed types: {', '.join(sorted(SUPPORTED_ORDER_TYPES))}"}

        # Validate price: Do not use arbitrary 100.0 fallback!
        if order_type in ["LIMIT", "STOP_LOSS"] and (price is None or price <= 0):
            return {"success": False, "error": f"A valid positive price is required for {order_type} orders."}

        if order_type == "MARKET" and (price is None or price <= 0):
            return {"success": False, "error": "Execution price is unavailable for MARKET order. Provide current market price."}

        order_id = f"ord_{uuid.uuid4().hex[:10]}"
        now = time.time()

        with _portfolio_lock, sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # -------------------------------------------------------------
            # 1. PENDING ORDERS (LIMIT & STOP_LOSS)
            # -------------------------------------------------------------
            if order_type in ["LIMIT", "STOP_LOSS"]:
                # If SELL limit or stop, verify position exists to prevent overselling
                if side == "SELL":
                    cursor.execute("SELECT quantity FROM paper_positions WHERE symbol = ? AND side = 'LONG';", (symbol,))
                    row = cursor.fetchone()
                    held_qty = row["quantity"] if row else 0
                    if held_qty < quantity:
                        return {"success": False, "error": f"Cannot place SELL {order_type} for {quantity} {symbol}; only {held_qty} held in position."}

                cursor.execute("""
                    INSERT INTO paper_orders (order_id, symbol, order_type, side, quantity, requested_price, executed_price, fee, status, pnl, notes, created_at, filled_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, 0.0, 'PENDING', 0.0, ?, ?, NULL);
                """, (order_id, symbol, order_type, side, quantity, price, f"Awaiting market price trigger for {order_type}", now))
                conn.commit()

                log_audit_event("paper_trade_queued", f"{order_type} {side} {quantity} {symbol} @ {price}", "safe", "pending")
                return {
                    "success": True,
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "quantity": quantity,
                    "requested_price": price,
                    "status": "PENDING",
                    "message": f"सिम्युलेटेड {order_type} ऑर्डर पंजीकृत (लंबित स्थिति): {side} {quantity} {symbol} @ ₹{price}"
                }

            # -------------------------------------------------------------
            # 2. MARKET ORDER EXECUTION
            # -------------------------------------------------------------
            cursor.execute("SELECT cash_balance FROM paper_account WHERE id = 1;")
            row = cursor.fetchone()
            cash = row["cash_balance"] if row else 1000000.0

            slippage_mult = (1.0 + SLIPPAGE_RATE + SPREAD_RATE) if side == "BUY" else (1.0 - SLIPPAGE_RATE - SPREAD_RATE)
            executed_price = round(price * slippage_mult, 2)
            trade_value = executed_price * quantity
            fee = COMMISSION_FLAT

            if side == "BUY":
                total_cost = trade_value + fee
                if cash < total_cost:
                    return {"success": False, "error": f"Insufficient simulated cash (Available: ₹{cash:.2f}, Required: ₹{total_cost:.2f})"}

                new_cash = cash - total_cost
                cursor.execute("UPDATE paper_account SET cash_balance = ?, updated_at = ? WHERE id = 1;", (new_cash, now))

                cursor.execute("SELECT * FROM paper_positions WHERE symbol = ? AND side = 'LONG';", (symbol,))
                existing_pos = cursor.fetchone()
                if existing_pos:
                    old_qty = existing_pos["quantity"]
                    old_entry = existing_pos["avg_entry_price"]
                    new_qty = old_qty + quantity
                    new_avg = round(((old_qty * old_entry) + trade_value) / new_qty, 2)
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

                cursor.execute("""
                    INSERT INTO paper_orders (order_id, symbol, order_type, side, quantity, requested_price, executed_price, fee, status, pnl, notes, created_at, filled_at)
                    VALUES (?, ?, 'MARKET', 'BUY', ?, ?, ?, ?, 'FILLED', 0.0, 'Simulated market fill', ?, ?);
                """, (order_id, symbol, quantity, price, executed_price, fee, now, now))

            elif side == "SELL":
                cursor.execute("SELECT * FROM paper_positions WHERE symbol = ? AND side = 'LONG';", (symbol,))
                existing_pos = cursor.fetchone()
                if not existing_pos or existing_pos["quantity"] < quantity:
                    avail = existing_pos["quantity"] if existing_pos else 0
                    return {"success": False, "error": f"Cannot sell {quantity} shares of {symbol}; only {avail} held."}

                old_qty = existing_pos["quantity"]
                entry_price = existing_pos["avg_entry_price"]
                gross_proceeds = executed_price * quantity
                net_proceeds = gross_proceeds - fee
                realized_pnl = round((executed_price - entry_price) * quantity - fee, 2)

                new_cash = cash + net_proceeds
                cursor.execute("UPDATE paper_account SET cash_balance = ?, updated_at = ? WHERE id = 1;", (new_cash, now))

                if old_qty == quantity:
                    cursor.execute("DELETE FROM paper_positions WHERE position_id = ?;", (existing_pos["position_id"],))
                else:
                    cursor.execute("""
                        UPDATE paper_positions SET quantity = ?, current_price = ?, updated_at = ? WHERE position_id = ?;
                    """, (old_qty - quantity, executed_price, now, existing_pos["position_id"]))

                cursor.execute("""
                    INSERT INTO paper_orders (order_id, symbol, order_type, side, quantity, requested_price, executed_price, fee, status, pnl, notes, created_at, filled_at)
                    VALUES (?, ?, 'MARKET', 'SELL', ?, ?, ?, ?, 'FILLED', ?, 'Simulated market fill', ?, ?);
                """, (order_id, symbol, quantity, price, executed_price, fee, realized_pnl, now, now))

            conn.commit()

        log_audit_event("paper_trade_order", f"{side} {quantity} {symbol} @ {executed_price}", "safe", "success")
        return {
            "success": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "order_type": "MARKET",
            "quantity": quantity,
            "executed_price": executed_price,
            "fee": fee,
            "status": "FILLED",
            "message": f"सिम्युलेटेड पेपर ऑर्डर निष्पादित: {side} {quantity} {symbol} @ ₹{executed_price} (शुल्क: ₹{fee})"
        }

    @classmethod
    def evaluate_pending_orders_and_triggers(cls, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """
        Evaluates pending LIMIT and STOP_LOSS orders and position TP/SL triggers
        against verified tick price updates.
        """
        if current_price <= 0:
            return []

        executions = []
        now = time.time()

        with _portfolio_lock, sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Evaluate Pending Orders for this Symbol
            cursor.execute("SELECT * FROM paper_orders WHERE symbol = ? AND status = 'PENDING';", (symbol,))
            pending_orders = [dict(r) for r in cursor.fetchall()]

            for ord_item in pending_orders:
                ord_id = ord_item["order_id"]
                ord_type = ord_item["order_type"]
                side = ord_item["side"]
                req_p = ord_item["requested_price"]
                qty = ord_item["quantity"]
                should_fill = False

                if ord_type == "LIMIT":
                    if side == "BUY" and current_price <= req_p:
                        should_fill = True
                    elif side == "SELL" and current_price >= req_p:
                        should_fill = True
                elif ord_type == "STOP_LOSS":
                    if side == "BUY" and current_price >= req_p:
                        should_fill = True
                    elif side == "SELL" and current_price <= req_p:
                        should_fill = True

                if should_fill:
                    # Execute fill
                    cursor.execute("SELECT cash_balance FROM paper_account WHERE id = 1;")
                    cash = cursor.fetchone()["cash_balance"]
                    fill_price = current_price
                    fee = COMMISSION_FLAT

                    if side == "BUY":
                        total_cost = (fill_price * qty) + fee
                        if cash >= total_cost:
                            cursor.execute("UPDATE paper_account SET cash_balance = ?, updated_at = ? WHERE id = 1;", (cash - total_cost, now))
                            cursor.execute("""
                                INSERT INTO paper_positions (position_id, symbol, side, quantity, avg_entry_price, current_price, created_at, updated_at)
                                VALUES (?, ?, 'LONG', ?, ?, ?, ?, ?);
                            """, (f"pos_{uuid.uuid4().hex[:10]}", symbol, qty, fill_price, fill_price, now, now))
                            cursor.execute("""
                                UPDATE paper_orders SET status = 'FILLED', executed_price = ?, fee = ?, filled_at = ?, notes = 'Limit/Stop filled at market'
                                WHERE order_id = ?;
                            """, (fill_price, fee, now, ord_id))
                            executions.append({"order_id": ord_id, "status": "FILLED", "fill_price": fill_price})
                    elif side == "SELL":
                        cursor.execute("SELECT * FROM paper_positions WHERE symbol = ? AND side = 'LONG';", (symbol,))
                        pos_row = cursor.fetchone()
                        if pos_row and pos_row["quantity"] >= qty:
                            realized = round((fill_price - pos_row["avg_entry_price"]) * qty - fee, 2)
                            net_proceeds = (fill_price * qty) - fee
                            cursor.execute("UPDATE paper_account SET cash_balance = ?, updated_at = ? WHERE id = 1;", (cash + net_proceeds, now))
                            if pos_row["quantity"] == qty:
                                cursor.execute("DELETE FROM paper_positions WHERE position_id = ?;", (pos_row["position_id"],))
                            else:
                                cursor.execute("UPDATE paper_positions SET quantity = ? WHERE position_id = ?;", (pos_row["quantity"] - qty, pos_row["position_id"]))
                            cursor.execute("""
                                UPDATE paper_orders SET status = 'FILLED', executed_price = ?, fee = ?, pnl = ?, filled_at = ?
                                WHERE order_id = ?;
                            """, (fill_price, fee, realized, now, ord_id))
                            executions.append({"order_id": ord_id, "status": "FILLED", "fill_price": fill_price, "pnl": realized})

            # 2. Evaluate Position TP/SL triggers
            cursor.execute("SELECT * FROM paper_positions WHERE symbol = ?;", (symbol,))
            positions = [dict(r) for r in cursor.fetchall()]
            for p in positions:
                sl = p["stop_loss"]
                tp = p["take_profit"]
                exit_reason = None
                if sl and current_price <= sl:
                    exit_reason = "STOP_LOSS_HIT"
                elif tp and current_price >= tp:
                    exit_reason = "TAKE_PROFIT_HIT"

                if exit_reason:
                    qty = p["quantity"]
                    entry = p["avg_entry_price"]
                    fee = COMMISSION_FLAT
                    realized = round((current_price - entry) * qty - fee, 2)
                    cursor.execute("SELECT cash_balance FROM paper_account WHERE id = 1;")
                    cash = cursor.fetchone()["cash_balance"]
                    cursor.execute("UPDATE paper_account SET cash_balance = ?, updated_at = ? WHERE id = 1;", (cash + (current_price * qty) - fee, now))
                    cursor.execute("DELETE FROM paper_positions WHERE position_id = ?;", (p["position_id"],))
                    cursor.execute("""
                        INSERT INTO paper_orders (order_id, symbol, order_type, side, quantity, requested_price, executed_price, fee, status, pnl, notes, created_at, filled_at)
                        VALUES (?, ?, 'MARKET', 'SELL', ?, ?, ?, ?, 'FILLED', ?, ?, ?, ?);
                    """, (f"ord_auto_{uuid.uuid4().hex[:8]}", symbol, qty, current_price, current_price, fee, realized, f"Auto-trigger: {exit_reason}", now, now))
                    executions.append({"symbol": symbol, "trigger": exit_reason, "pnl": realized})

            conn.commit()

        return executions

    @classmethod
    def reset_account(
        cls,
        initial_capital: float = 1000000.0,
        confirmed: bool = True,
        purge_history: bool = False
    ) -> Dict[str, Any]:
        """
        Resets the paper trading account with mandatory confirmation and snapshot backup.
        Historical orders are preserved unless purge_history is explicitly True.
        """
        if not confirmed:
            return {
                "success": False,
                "error": "Account reset requires explicit confirmation (confirmed=True)."
            }

        with _portfolio_lock, sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Fetch current state for reversible snapshot backup
            cursor.execute("SELECT * FROM paper_account WHERE id = 1;")
            acc = dict(cursor.fetchone() or {"cash_balance": 1000000.0, "initial_capital": 1000000.0})
            cursor.execute("SELECT * FROM paper_positions;")
            pos_list = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT * FROM paper_orders;")
            orders_list = [dict(r) for r in cursor.fetchall()]

            # 2. Store Snapshot Backup
            snap_id = f"snap_{uuid.uuid4().hex[:10]}"
            cursor.execute("""
                INSERT INTO paper_account_snapshots (snapshot_id, timestamp, initial_capital, cash_balance, positions_json, orders_json)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (snap_id, time.time(), acc["initial_capital"], acc["cash_balance"], json.dumps(pos_list), json.dumps(orders_list)))

            # 3. Apply Reversible Reset
            cursor.execute("UPDATE paper_account SET initial_capital = ?, cash_balance = ?, updated_at = ? WHERE id = 1;", (initial_capital, initial_capital, time.time()))
            cursor.execute("DELETE FROM paper_positions;")

            if purge_history:
                cursor.execute("DELETE FROM paper_orders;")
            else:
                cursor.execute("UPDATE paper_orders SET status = 'ARCHIVED' WHERE status = 'PENDING';")

            conn.commit()

        log_audit_event("reset_paper_account", f"Capital: {initial_capital}, Snapshot: {snap_id}", "high", "success")
        return {
            "success": True,
            "snapshot_id": snap_id,
            "message": f"पेपर ट्रेडिंग अकाउंट ₹{initial_capital:,.2f} पर सुरक्षित रूप से रीसेट कर दिया गया है। (स्नैपशॉट बैकअप: {snap_id})"
        }
