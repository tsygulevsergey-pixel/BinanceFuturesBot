"""
Configuration settings for Binance Futures Scanner Bot
Based on technical specification requirements
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MODE = 'SIGNAL_ONLY'
    
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
    BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
    
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    PROXY = {
        'http': 'http://fyplvqgw:04azcek13s9n@23.27.184.165:5766',
        'https': 'http://fyplvqgw:04azcek13s9n@23.27.184.165:5766'
    }
    
    PROXY_URL = 'http://fyplvqgw:04azcek13s9n@23.27.184.165:5766'
    
    UNIVERSE_RESCAN_INTERVAL = 1 * 3600  # 1 hour for faster universe updates
    
    MIN_24H_VOLUME = 30_000_000  # Stage 1: Initial volume filter
    MIN_OPEN_INTEREST = 1_000_000  # Stage 2: Open interest filter ($1M)
    MAX_SPREAD = 0.0002  # Stage 3: Fixed spread filter (0.02%)
    
    USE_DYNAMIC_SPREAD = False  # Use ATR-based dynamic spread filter (disabled for now)
    DYNAMIC_SPREAD_ATR_MULTIPLIER = 0.1  # Spread <= 10% of ATR
    
    OI_CONCURRENT_LIMIT = 10  # Max concurrent open interest requests
    
    # Blacklist: symbols to exclude from universe
    SYMBOL_BLACKLIST = [
        'BTCDOMUSDT',  # Bitcoin Dominance Index
        'DEFIUSDT',    # DeFi Index
        'ETHBTCUSDT',  # ETH/BTC ratio (not a real coin)
    ]
    
    # Filter out symbols with non-ASCII characters (Chinese, Japanese, etc.)
    FILTER_NON_ASCII = True
    
    # GLOBAL IMBALANCE (200 levels): thresholds LOWERED by ~40% compared to local (10 levels)
    # Global imbalance is more smoothed, typically 0.05-0.20 vs local 0.25-0.50
    ORDERBOOK_IMBALANCE_THRESHOLD = 0.15  # Minimum GLOBAL imbalance for signal (was 0.25 for local)
    MIN_LARGE_TRADES = 2                  # Minimum large trades required
    
    # Large trade detection: DYNAMIC (percentile-based) approach
    USE_DYNAMIC_LARGE_TRADES = True        # Use percentile-based (top 1%) instead of fixed threshold
    LARGE_TRADE_PERCENTILE = 99            # 99th percentile = top 1% of trade sizes
    MIN_LARGE_TRADE_SIZE = 10_000          # Minimum threshold ($10K) as fallback for low-liquidity pairs
    LARGE_TRADE_SIZE = 50_000              # Legacy fixed threshold (used when USE_DYNAMIC_LARGE_TRADES=False)
    
    VOLUME_CONFIRMATION_MULTIPLIER = 1.5   # Reduced from 1.8 for more realistic filtering
    
    PRIMARY_TF = '15m'
    CONTEXT_TF = '1h'
    
    MAX_DAILY_SIGNALS = 999999  # No limit (user request)
    MAX_CONCURRENT_SIGNALS = 999999  # No limit (user request)
    CORRELATION_THRESHOLD = 0.6
    
    ORDERBOOK_DEPTH = 20
    TRADE_HISTORY_WINDOW = 300
    KLINE_HISTORY_BARS = 100
    UPDATE_FREQUENCY = 100
    
    SIGNAL_QUALITY_WEIGHTS = {
        'orderbook_imbalance': 35,
        'volume_confirmation': 30,
        'large_trades': 35
    }
    
    PRIORITY_LEVELS = {
        'HIGH': {
            'max_daily': 20,
            'min_quality': 80,
            'hold_time_min': 15,
            'hold_time_max': 45
        },
        'MEDIUM': {
            'max_daily': 40,
            'min_quality': 65,
            'hold_time_min': 30,
            'hold_time_max': 90
        },
        'LOW': {
            'max_daily': 20,
            'min_quality': 50,
            'hold_time_min': 60,
            'hold_time_max': 180
        }
    }
    
    BINANCE_RATE_LIMIT_WEIGHT = 2400
    BINANCE_RATE_LIMIT_ORDERS = 1200
    
    REDIS_HOST = '127.0.0.1'
    REDIS_PORT = 6379
    REDIS_DB = 0
    
    # Fast Signal Tracker - 100ms hybrid exit strategy
    FAST_TRACKING_INTERVAL = 0.1  # 100ms check interval
    CACHE_SYNC_INTERVAL = 5        # Sync cache from DB every 5 seconds
    
    # Hybrid exit thresholds
    # IMBALANCE_EXIT_NORMALIZED = 0.2   # DISABLED - was causing premature exits with -PnL
    IMBALANCE_EXIT_REVERSED = 0.4     # Exit when opposite imbalance > 0.4 (RAISED from 0.3 to reduce noise)
    MIN_HOLD_TIME_SECONDS = 30        # Minimum hold time before allowing IMBALANCE_REVERSED exit
    
    # EXIT Persistence filter: require SUSTAINED reversal before exiting
    # This prevents exits on temporary imbalance spikes (noise)
    IMBALANCE_REVERSAL_PERSISTENCE_SAMPLES = 75  # 75 samples × 100ms = 7.5 seconds confirmation
    
    # ENTRY Persistence filter: require SUSTAINED confluence before creating signal
    # This prevents signal creation on temporary spikes (noise filtering)
    SIGNAL_ENTRY_PERSISTENCE_SAMPLES = 50  # 50 samples × 100ms = 5 seconds confirmation
    
    # Priority thresholds for GLOBAL imbalance (200 levels)
    PRIORITY_HIGH_THRESHOLD = 0.25     # HIGH: ≥25% global imbalance (was 0.35 for local)
    PRIORITY_MEDIUM_THRESHOLD = 0.20   # MEDIUM: ≥20% global imbalance (was 0.30 for local)
    
    # Partial close settings
    PARTIAL_CLOSE_TP1_PERCENT = 0.5  # Close 50% of position on TP1
    PARTIAL_CLOSE_TP2_PERCENT = 0.5  # Close remaining 50% on TP2
    MOVE_SL_TO_BREAKEVEN = True      # Move SL to entry price after TP1 hit
    
    # === DYNAMIC SL/TP SYSTEM (Orderbook-based levels) ===
    
    # Stop Loss Settings
    MIN_STOP_DISTANCE_PCT = 0.15  # Минимальное расстояние стопа от входа (%) - защита от микро-движений
    MAX_STOP_DISTANCE_PCT = 1.5   # Максимальное расстояние стопа от входа (%)
    
    # Take Profit Settings
    MIN_TP_DISTANCE_PCT = 0.50    # Минимальное расстояние TP от входа (%) - защита от комиссий
    MIN_RR_RATIO = 0.8            # Минимальный Risk/Reward ratio для принятия сигнала
    
    # Orderbook Analysis Settings
    ORDERBOOK_DEPTH_LEVELS = 50  # Глубина анализа стакана (уровней)
    CLUSTER_THRESHOLD_MULTIPLIER = 2.0  # Объем > среднего в 2x = кластер
    LOW_VOLUME_THRESHOLD = 0.5  # Объем < среднего в 2x = зона низкого объема
    MIN_VOLUME_PCT_FOR_LEVEL = 10.0  # Минимум 10% от макс объема для значимого уровня
    
    # Volume Profile Settings (объемные зоны)
    VOLUME_PROFILE_HOURS = 6  # Анализировать объем за последние 6 часов (актуальные данные)
    
    # Volatility Settings
    ATR_PERIOD = 14  # Количество свечей для расчета ATR
    WORKING_RANGE_ATR_MULTIPLIER = 3.0  # Рабочий диапазон = ±3 ATR от цены
    
    # Volatility Categories (для адаптации ширины стопа)
    VOLATILITY_CATEGORIES = {
        'LOW': 0.3,      # <0.3% ATR - BTC, ETH
        'MEDIUM': 0.7,   # 0.3-0.7% ATR - большинство альтов
        'HIGH': float('inf')  # >0.7% ATR - мемкоины
    }
    
    # NOTE: Priority thresholds moved up (lines 128-130) - adjusted for GLOBAL imbalance (200 levels)
    # PRIORITY_HIGH_THRESHOLD = 0.25 (was 0.35 for local 10 levels)
    # PRIORITY_MEDIUM_THRESHOLD = 0.20 (was 0.30 for local 10 levels)
    
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'bot/logs/bot.log'
