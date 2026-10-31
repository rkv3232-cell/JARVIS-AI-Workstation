import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import Optional, Any
from .config import settings

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis_memory.db"

# Global Firestore client handle
_firestore_db = None
_firebase_initialized = False

def _bg_firestore_write(collection_name: str, doc_data: dict):
    """
    Asynchronous non-blocking background writer to Firebase Firestore.
    Guarantees 0ms delay on user conversation pipeline.
    """
    try:
        fdb = get_firestore_client()
        if fdb:
            fdb.collection(collection_name).add(doc_data)
    except Exception as e:
        print(f"[Firebase Async Notice]: {e}")

def get_firestore_client():
    global _firestore_db, _firebase_initialized
    if _firestore_db is not None:
        return _firestore_db
    
    try:
        import firebase_admin
        from firebase_admin import firestore
        
        project_id = settings.FIREBASE_PROJECT_ID or "eduosai"
        cred_path = settings.FIREBASE_CREDENTIALS_PATH
        
        if not firebase_admin._apps:
            if cred_path and Path(cred_path).exists():
                from firebase_admin import credentials
                cred = credentials.Certificate(cred_path)
                app = firebase_admin.initialize_app(cred, options={"projectId": project_id})
            else:
                app = firebase_admin.initialize_app(options={"projectId": project_id})
        else:
            app = firebase_admin.get_app()
            
        _firestore_db = firestore.client(app=app)
        _firebase_initialized = True
        print(f"[Firebase] Successfully connected to Firestore project: '{project_id}'")
        return _firestore_db
    except Exception as e:
        print(f"[Firebase Warning] Firestore init fallback to SQLite: {e}")
        return None

def init_db():
    """
    Initializes both local SQLite cache and verifies Firebase connection.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Conversation logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            intent TEXT,
            timestamp REAL NOT NULL
        )
    """)
    
    # 2. System audit logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            status TEXT NOT NULL,
            output TEXT,
            timestamp REAL NOT NULL
        )
    """)
    
    # 3. Trade signals history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            price REAL NOT NULL,
            risk_reward REAL NOT NULL,
            details TEXT,
            timestamp REAL NOT NULL
        )
    """)

    # 4. Trading Journal
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            symbol TEXT NOT NULL,
            outcome TEXT,
            notes TEXT,
            psychology_tags TEXT,
            pnl REAL DEFAULT 0.0,
            timestamp REAL NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()

    # Pre-warm Firestore client
    get_firestore_client()

def log_conversation(role: str, content: str, intent: str = "general", metadata: Optional[dict] = None):
    now = time.time()
    # 1. Ultra-fast Write to Local SQLite (<1ms)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversation_history (role, content, intent, timestamp) VALUES (?, ?, ?, ?)",
            (role, content, intent, now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB Error] SQLite log_conversation: {e}")

    # 2. Async Non-Blocking Write to Firebase Firestore in Background (0ms latency impact)
    doc_data = {
        "role": role,
        "content": content,
        "intent": intent,
        "timestamp": now,
        "metadata": metadata or {}
    }
    threading.Thread(target=_bg_firestore_write, args=("jarvis_conversations", doc_data), daemon=True).start()

def get_recent_history(limit: int = 15) -> list[dict]:
    # 1. Read instantly from local SQLite (<1ms)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM conversation_history ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        if rows:
            items = []
            for r in rows:
                role = "assistant" if r[0] == "jarvis" else ("user" if r[0] == "user" else "assistant")
                items.append({"role": role, "content": r[1]})
            items.reverse()
            return items
    except Exception as e:
        print(f"[DB Error] SQLite get_recent_history: {e}")

    # 2. Fallback to Firebase Firestore if SQLite has no records
    try:
        fdb = get_firestore_client()
        if fdb:
            docs = fdb.collection("jarvis_conversations")\
                      .order_by("timestamp", direction="DESCENDING")\
                      .limit(limit)\
                      .stream()
            items = []
            for d in docs:
                data = d.to_dict()
                role = "assistant" if data.get("role") == "jarvis" else ("user" if data.get("role") == "user" else "assistant")
                items.append({"role": role, "content": data.get("content", "")})
            if items:
                items.reverse()
                return items
    except Exception as e:
        print(f"[Firebase Notice] get_recent_history fallback: {e}")

    return []

def log_trade_alert(symbol: str, signal_type: str, timeframe: str, price: float, risk_reward: float, details: dict):
    now = time.time()
    # 1. SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO trade_alerts (symbol, signal_type, timeframe, price, risk_reward, details, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (symbol, signal_type, timeframe, price, risk_reward, json.dumps(details), now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB Error] SQLite log_trade_alert: {e}")

    # 2. Firebase Firestore
    try:
        fdb = get_firestore_client()
        if fdb:
            fdb.collection("jarvis_trade_alerts").add({
                "symbol": symbol,
                "signal_type": signal_type,
                "timeframe": timeframe,
                "price": price,
                "risk_reward": risk_reward,
                "details": details,
                "timestamp": now
            })
    except Exception as e:
        print(f"[Firebase Error] log_trade_alert: {e}")

def get_recent_trade_alerts(limit: int = 20) -> list[dict]:
    # 1. Try Firebase Firestore
    try:
        fdb = get_firestore_client()
        if fdb:
            docs = fdb.collection("jarvis_trade_alerts")\
                      .order_by("timestamp", direction="DESCENDING")\
                      .limit(limit)\
                      .stream()
            alerts = [d.to_dict() for d in docs]
            if alerts:
                return alerts
    except Exception:
        pass

    # 2. Fallback SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT symbol, signal_type, timeframe, price, risk_reward, details, timestamp FROM trade_alerts ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        results = []
        for r in rows:
            try:
                det = json.loads(r[5])
            except Exception:
                det = {}
            results.append({
                "symbol": r[0],
                "signal_type": r[1],
                "timeframe": r[2],
                "price": r[3],
                "risk_reward": r[4],
                "details": det,
                "timestamp": r[6]
            })
        return results
    except Exception as e:
        print(f"[DB Error] get_recent_trade_alerts: {e}")
        return []

def log_action_audit(command: str, status: str, output: str = ""):
    now = time.time()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO action_audit_logs (command, status, output, timestamp) VALUES (?, ?, ?, ?)",
            (command, status, output, now)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    try:
        fdb = get_firestore_client()
        if fdb:
            fdb.collection("jarvis_action_logs").add({
                "command": command,
                "status": status,
                "output": output[:500],
                "timestamp": now
            })
    except Exception:
        pass

def save_trading_journal_entry(title: str, symbol: str, outcome: str, notes: str, psychology_tags: list[str], pnl: float = 0.0) -> dict:
    now = time.time()
    entry = {
        "title": title,
        "symbol": symbol.upper(),
        "outcome": outcome,
        "notes": notes,
        "psychology_tags": psychology_tags,
        "pnl": pnl,
        "timestamp": now
    }
    # SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO trading_journal (title, symbol, outcome, notes, psychology_tags, pnl, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, symbol.upper(), outcome, notes, json.dumps(psychology_tags), pnl, now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB Error] save_trading_journal_entry: {e}")

    # Firebase
    try:
        fdb = get_firestore_client()
        if fdb:
            fdb.collection("jarvis_trading_journal").add(entry)
    except Exception as e:
        print(f"[Firebase Error] save_trading_journal_entry: {e}")

    return entry

def get_trading_journal(limit: int = 20) -> list[dict]:
    try:
        fdb = get_firestore_client()
        if fdb:
            docs = fdb.collection("jarvis_trading_journal")\
                      .order_by("timestamp", direction="DESCENDING")\
                      .limit(limit)\
                      .stream()
            journal = [d.to_dict() for d in docs]
            if journal:
                return journal
    except Exception:
        pass

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT title, symbol, outcome, notes, psychology_tags, pnl, timestamp FROM trading_journal ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        results = []
        for r in rows:
            try:
                tags = json.loads(r[4])
            except Exception:
                tags = []
            results.append({
                "title": r[0],
                "symbol": r[1],
                "outcome": r[2],
                "notes": r[3],
                "psychology_tags": tags,
                "pnl": r[5],
                "timestamp": r[6]
            })
        return results
    except Exception as e:
        print(f"[DB Error] get_trading_journal: {e}")
        return []

# Initialize database on import
init_db()
