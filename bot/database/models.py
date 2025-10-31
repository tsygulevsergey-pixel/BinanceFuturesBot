"""
PostgreSQL database models for storing all historical data
Tables: symbols, signals, trades, performance_metrics, daily_stats
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text, Index, ForeignKey, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import uuid

Base = declarative_base()

class Symbol(Base):
    __tablename__ = 'symbols'
    
    id = Column(String(50), primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    score = Column(Float, default=0.0)
    volume_24h = Column(Numeric(20, 2), default=0)
    open_interest = Column(Numeric(20, 2), default=0)
    liquidity_score = Column(Float, default=0.0)
    volatility_score = Column(Float, default=0.0)
    activity_score = Column(Float, default=0.0)
    spread = Column(Float, default=0.0)
    trades_24h = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        Index('idx_symbol_active', 'is_active'),
        Index('idx_symbol_score', 'score'),
    )

class Signal(Base):
    __tablename__ = 'signals'
    
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String(20), ForeignKey('symbols.symbol'), nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    signal_type = Column(String(10), default='ENTRY')
    priority = Column(String(10), nullable=False, index=True)
    
    entry_price = Column(Numeric(20, 8), nullable=False)
    stop_loss = Column(Numeric(20, 8), nullable=False)
    take_profit_1 = Column(Numeric(20, 8), nullable=False)
    take_profit_2 = Column(Numeric(20, 8), nullable=False)
    
    quality_score = Column(Float, nullable=False)
    orderbook_imbalance = Column(Float, nullable=False)
    large_trades_count = Column(Integer, nullable=False)
    volume_intensity = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    
    suggested_position_size = Column(Float, default=0.01)
    risk_reward_ratio = Column(Float, default=0.0)
    expected_hold_time = Column(String(20), default='')
    
    # Dynamic SL/TP reasoning (NEW - orderbook-based levels)
    stop_loss_reason = Column(String(200), nullable=True)  # "Below support at 42800"
    tp1_reason = Column(String(200), nullable=True)  # "First resistance at 43800"
    tp2_reason = Column(String(200), nullable=True)  # "Second resistance at 44500"
    support_level = Column(Numeric(20, 8), nullable=True)  # Ближайший support (для LONG)
    resistance_level = Column(Numeric(20, 8), nullable=True)  # Ближайший resistance (для SHORT)
    
    status = Column(String(20), default='OPEN', index=True)
    telegram_message_id = Column(Integer, nullable=True)
    
    # Partial close tracking (NEW - for 50/50 TP1/TP2 strategy)
    tp1_hit_price = Column(Numeric(20, 8), nullable=True)
    tp1_hit_time = Column(DateTime, nullable=True)
    tp1_pnl = Column(Numeric(10, 4), nullable=True)  # PnL from TP1 (50% of position)
    
    tp2_hit_price = Column(Numeric(20, 8), nullable=True)
    tp2_hit_time = Column(DateTime, nullable=True)
    tp2_pnl = Column(Numeric(10, 4), nullable=True)  # PnL from TP2 (remaining 50%)
    
    partial_close_status = Column(String(20), default='NONE')  # 'NONE', 'TP1_CLOSED', 'FULLY_CLOSED'
    breakeven_moved = Column(Boolean, default=False)  # True if SL moved to breakeven after TP1
    current_stop_loss = Column(Numeric(20, 8), nullable=True)  # Updated SL (breakeven or original)
    
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_signal_status', 'status'),
        Index('idx_signal_created', 'created_at'),
        Index('idx_signal_symbol_status', 'symbol', 'status'),
    )

class Trade(Base):
    __tablename__ = 'trades'
    
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_id = Column(String(50), ForeignKey('signals.id'), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    
    entry_price = Column(Numeric(20, 8), nullable=False)
    exit_price = Column(Numeric(20, 8), nullable=True)
    stop_loss = Column(Numeric(20, 8), nullable=False)
    take_profit_1 = Column(Numeric(20, 8), nullable=False)
    take_profit_2 = Column(Numeric(20, 8), nullable=False)
    
    exit_reason = Column(String(30), nullable=True)  # Extended for 'STOP_LOSS_BREAKEVEN'
    pnl = Column(Numeric(20, 8), nullable=True)
    pnl_percent = Column(Float, nullable=True)
    
    # Partial close tracking (NEW - for Trade history)
    tp1_hit_price = Column(Numeric(20, 8), nullable=True)
    tp1_hit_time = Column(DateTime, nullable=True)
    tp1_pnl = Column(Numeric(10, 4), nullable=True)
    
    tp2_hit_price = Column(Numeric(20, 8), nullable=True)
    tp2_hit_time = Column(DateTime, nullable=True)
    tp2_pnl = Column(Numeric(10, 4), nullable=True)
    
    partial_close_status = Column(String(20), nullable=True)  # Final status when closed
    
    # Dynamic SL/TP reasoning (копия из Signal для исторических данных)
    stop_loss_reason = Column(String(200), nullable=True)
    tp1_reason = Column(String(200), nullable=True)
    tp2_reason = Column(String(200), nullable=True)
    support_level = Column(Numeric(20, 8), nullable=True)
    resistance_level = Column(Numeric(20, 8), nullable=True)
    
    hold_time_minutes = Column(Integer, nullable=True)
    
    status = Column(String(20), default='OPEN', index=True)
    
    entry_time = Column(DateTime, default=func.now(), index=True)
    exit_time = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_trade_status', 'status'),
        Index('idx_trade_entry_time', 'entry_time'),
    )

class PerformanceMetrics(Base):
    __tablename__ = 'performance_metrics'
    
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(DateTime, nullable=False, index=True)
    
    signals_generated = Column(Integer, default=0)
    signals_triggered = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    
    total_pnl = Column(Numeric(20, 8), default=0)
    average_pnl = Column(Numeric(20, 8), default=0)
    max_profit = Column(Numeric(20, 8), default=0)
    max_loss = Column(Numeric(20, 8), default=0)
    
    average_hold_time = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    
    tp1_hit_count = Column(Integer, default=0)
    tp2_hit_count = Column(Integer, default=0)
    sl_hit_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        Index('idx_perf_date', 'date'),
    )

class DailyStats(Base):
    __tablename__ = 'daily_stats'
    
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(DateTime, nullable=False, unique=True, index=True)
    
    total_signals = Column(Integer, default=0)
    high_priority_signals = Column(Integer, default=0)
    medium_priority_signals = Column(Integer, default=0)
    low_priority_signals = Column(Integer, default=0)
    
    active_symbols_count = Column(Integer, default=0)
    best_symbol = Column(String(20), nullable=True)
    worst_symbol = Column(String(20), nullable=True)
    
    win_rate = Column(Float, default=0.0)
    total_pnl = Column(Numeric(20, 8), default=0)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
