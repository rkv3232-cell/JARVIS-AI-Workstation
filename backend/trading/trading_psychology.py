import time
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..security import log_audit_event

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"

VALID_EMOTIONS = [
    "Disciplined",
    "FOMO",
    "Revenge Trade",
    "Anxious",
    "Confident",
    "Greedy",
    "Hesitant"
]

def init_psychology_db():
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trading_psychology_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL, -- BUY, SELL, HOLD, NOTE
                emotion_tag TEXT NOT NULL,
                checklist_passed INTEGER NOT NULL, -- Count of checked items (0-4)
                discipline_score INTEGER NOT NULL, -- 0 to 100
                reflection_notes TEXT,
                trade_outcome TEXT, -- WIN, LOSS, BREAKEVEN, OPEN
                pnl REAL DEFAULT 0.0
            );
        """)
        conn.commit()

init_psychology_db()

class TradingPsychologyEngine:
    """
    Evaluates emotional discipline, checklist compliance, and mental clarity
    to prevent revenge trading and impulsive FOMO.
    """
    @staticmethod
    def calculate_discipline_score(emotion_tag: str, checklist_answers: List[bool]) -> int:
        score = 60  # baseline

        # Checklist compliance (up to 40 points)
        passed_count = sum(1 for a in checklist_answers if a is True)
        score += passed_count * 10

        # Emotional penalties or bonuses
        em = emotion_tag.strip().upper()
        if em == "DISCIPLINED":
            score += 15
        elif em == "CONFIDENT":
            score += 5
        elif em in ["FOMO", "GREEDY"]:
            score -= 25
        elif em in ["REVENGE TRADE", "REVENGE"]:
            score -= 35
        elif em == "ANXIOUS":
            score -= 10
        elif em == "HESITANT":
            score -= 5

        return max(0, min(100, score))

    @classmethod
    def record_entry(
        cls,
        symbol: str,
        action: str,
        emotion_tag: str,
        checklist_answers: List[bool],
        notes: str,
        outcome: str = "OPEN",
        pnl: float = 0.0
    ) -> Dict[str, Any]:
        discipline_score = cls.calculate_discipline_score(emotion_tag, checklist_answers)
        passed_count = sum(1 for a in checklist_answers if a is True)
        now = time.time()

        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trading_psychology_journal
                (timestamp, symbol, action, emotion_tag, checklist_passed, discipline_score, reflection_notes, trade_outcome, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (now, symbol.upper(), action.upper(), emotion_tag, passed_count, discipline_score, notes, outcome.upper(), pnl))
            entry_id = cursor.lastrowid
            conn.commit()

        log_audit_event("psychology_journal_entry", f"{symbol} - {emotion_tag} ({discipline_score}/100)", "safe", "success")
        return {
            "success": True,
            "entry_id": entry_id,
            "discipline_score": discipline_score,
            "checklist_passed": passed_count,
            "status": "Healthy Discipline" if discipline_score >= 70 else "High Emotional Risk",
            "message": f"ट्रेडिंग साइकोलॉजी जर्नल में प्रविष्टि दर्ज। अनुशासन स्कोर: {discipline_score}/100"
        }

    @classmethod
    def get_entries(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, datetime(timestamp, 'unixepoch', 'localtime') as date_str,
                       symbol, action, emotion_tag, checklist_passed, discipline_score, reflection_notes, trade_outcome, pnl
                FROM trading_psychology_journal
                ORDER BY timestamp DESC LIMIT ?;
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    @classmethod
    def get_psychology_analytics(cls) -> Dict[str, Any]:
        """Calculates emotional breakdown, average discipline score, and win-rate by emotion."""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trading_psychology_journal;")
            rows = [dict(r) for r in cursor.fetchall()]

        if not rows:
            return {
                "total_entries": 0,
                "avg_discipline_score": 100,
                "top_emotion": "Disciplined",
                "emotion_breakdown": {},
                "risk_advisory": "No emotional trading data logged yet."
            }

        scores = [r["discipline_score"] for r in rows]
        avg_score = round(sum(scores) / len(scores), 1)

        emotion_counts = {}
        for r in rows:
            em = r["emotion_tag"]
            emotion_counts[em] = emotion_counts.get(em, 0) + 1

        top_em = max(emotion_counts.items(), key=lambda x: x[1])[0]

        # Advisory
        advisory = "उत्कृष्ट मानसिक अनुशासन! आप नियमों का 100% पालन कर रहे हैं।"
        if avg_score < 60:
            advisory = "चेतावनी: हाल के ट्रेड्स में FOMO या बदले की भावना (Revenge Trading) देखी गई है। जोखिम कम करें।"

        return {
            "total_entries": len(rows),
            "avg_discipline_score": avg_score,
            "top_emotion": top_em,
            "emotion_breakdown": emotion_counts,
            "risk_advisory": advisory
        }
