from typing import Optional, Any
from pydantic import BaseModel, Field
import time

class ChatRequest(BaseModel):
    message: str = Field(..., description="User voice transcript or typed text")
    source: str = Field(default="voice", description="Input modality: 'voice' or 'text'")

class ChatResponse(BaseModel):
    text: str
    audio_url: Optional[str] = None
    action_executed: Optional[str] = None
    intent: str
    dynamic_widget: Optional[dict] = None
    timestamp: float = Field(default_factory=time.time)

class SystemTelemetry(BaseModel):
    cpu_percent: float
    cpu_freq_current: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disk_percent: float
    disk_free_gb: float
    battery_percent: Optional[float] = None
    is_charging: Optional[bool] = None
    network_sent_mb: float
    network_recv_mb: float
    timestamp: float = Field(default_factory=time.time)

class TradeSignal(BaseModel):
    symbol: str
    signal_type: str  # BULLISH_OB, BEARISH_OB, BULLISH_FVG, BEARISH_FVG, LIQUIDITY_SWEEP
    timeframe: str
    current_price: float
    entry_zone: list[float]
    stop_loss: float
    take_profit: float
    risk_reward: float
    description: str
    mtf_bias: Optional[str] = "NEUTRAL"
    unmitigated: bool = True
    timestamp: float = Field(default_factory=time.time)

class OptionStrike(BaseModel):
    strike: float
    call_oi: int
    call_chg_oi: int
    call_ltp: float
    put_oi: int
    put_chg_oi: int
    put_ltp: float

class OptionChainData(BaseModel):
    symbol: str
    spot_price: float
    pcr: float
    max_pain: float
    sentiment: str  # BULLISH, BEARISH, NEUTRAL, RANGEBOUND
    strikes: list[OptionStrike]
    india_vix: float
    timestamp: float = Field(default_factory=time.time)

class MorningBriefing(BaseModel):
    gift_nifty: float
    gift_nifty_change: float
    us_markets_summary: str
    dxy: float
    crude_oil: float
    nifty_support: list[float]
    nifty_resistance: list[float]
    economic_events: list[str]
    spoken_brief: str
    timestamp: float = Field(default_factory=time.time)

class WSMessage(BaseModel):
    event: str  # "telemetry", "chat_response", "chat_audio", "trade_alert", "option_chain", "morning_briefing"
    payload: Any
    timestamp: float = Field(default_factory=time.time)
