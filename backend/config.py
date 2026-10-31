import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings(BaseModel):
    BASE_DIR: Path = BASE_DIR
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # Voice Settings
    JARVIS_LANG: str = os.getenv("JARVIS_LANG", "hi")
    JARVIS_VOICE: str = os.getenv("JARVIS_VOICE", "hi-IN-MadhurNeural")
    
    # AI API Keys & Multi-Key Pools
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_KEY_1: str = os.getenv("GEMINI_API_KEY_1", "")
    GEMINI_API_KEY_2: str = os.getenv("GEMINI_API_KEY_2", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    @property
    def gemini_keys_pool(self) -> list[str]:
        """Returns all non-empty Gemini API keys in priority order."""
        return [k.strip() for k in [self.GEMINI_API_KEY, self.GEMINI_API_KEY_1, self.GEMINI_API_KEY_2] if k and k.strip()]
    
    # Specialized Free AI Model Routing
    MODEL_CHAT: str = os.getenv("MODEL_CHAT", "qwen/qwen3.8-27b")
    MODEL_CODING: str = os.getenv("MODEL_CODING", "openai/gpt-oss-120b")
    MODEL_REASONING: str = os.getenv("MODEL_REASONING", "openai/gpt-oss-120b")
    MODEL_VISION: str = os.getenv("MODEL_VISION", "gemini-3.5-flash-lite")
    MODEL_FACT_CHECK: str = os.getenv("MODEL_FACT_CHECK", "openai/gpt-oss-120b")
    MODEL_RESEARCH_WRITER: str = os.getenv("MODEL_RESEARCH_WRITER", "gemini-3.5-flash-lite")
    MODEL_RESEARCH_VOICE: str = os.getenv("MODEL_RESEARCH_VOICE", "qwen/qwen3.8-27b")
    MODEL_STT: str = os.getenv("MODEL_STT", "whisper-large-v3-turbo")

    # Sarvam AI Voice & Indic Intelligence Settings
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
    SARVAM_SPEAKER: str = os.getenv("SARVAM_SPEAKER", "shubh")
    SARVAM_MODEL: str = os.getenv("SARVAM_MODEL", "bulbul:v3")
    SARVAM_STT_MODEL: str = os.getenv("SARVAM_STT_MODEL", "saaras:v4")
    SARVAM_PACE: float = float(os.getenv("SARVAM_PACE", "1.06"))
    
    # Trading Defaults
    DEFAULT_SYMBOLS: list[str] = [
        s.strip() for s in os.getenv("DEFAULT_SYMBOLS", "NIFTY50,BANKNIFTY,BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()
    ]
    SCANNER_INTERVAL_SECONDS: int = int(os.getenv("SCANNER_INTERVAL_SECONDS", "30"))
    MIN_RISK_REWARD: float = float(os.getenv("MIN_RISK_REWARD", "2.0"))

    # Firebase Firestore Settings
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "eduosai")
    FIREBASE_CREDENTIALS_PATH: str = os.getenv("FIREBASE_CREDENTIALS_PATH", "")

    # Privacy & Automation Defaults
    ENABLE_SCREEN_VISION: bool = os.getenv("ENABLE_SCREEN_VISION", "True").lower() == "true"
    ENABLE_WAKE_WORD_DEFAULT: bool = os.getenv("ENABLE_WAKE_WORD_DEFAULT", "False").lower() == "true"
    MORNING_BRIEFING_TIME: str = os.getenv("MORNING_BRIEFING_TIME", "09:00")
    DEFAULT_USER_CITY: str = os.getenv("USER_LOCATION", "Dullahpur, Uttar Pradesh")

    # Security & Session
    SESSION_TOKEN: str = os.getenv("SESSION_TOKEN", "jarvis-apex-session-key-v2")
    ALLOWED_ORIGINS: list[str] = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "pywebview://localhost",
        "http://localhost",
        "http://127.0.0.1"
    ]
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # Ollama Local Private LLM
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

settings = Settings()
