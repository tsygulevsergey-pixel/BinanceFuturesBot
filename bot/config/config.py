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
    
    ORDERBOOK_IMBALANCE_THRESHOLD = 0.35  # RAISED from 0.2 to filter weak signals (was 0.28)
    MIN_LARGE_TRADES = 2                  # Reduced from 3 to allow more signals
    
    # Large trade detection: DYNAMIC (percentile-based) approach
    USE_DYNAMIC_LARGE_TRADES = True        # Use percentile-based (top 1%) instead of fixed threshold
    LARGE_TRADE_PERCENTILE = 99            # 99th percentile = top 1% of trade sizes
    MIN_LARGE_TRADE_SIZE = 10_000          # Minimum threshold ($10K) as fallback for low-liquidity pairs
    LARGE_TRADE_SIZE = 50_000              # Legacy fixed threshold (used when USE_DYNAMIC_LARGE_TRADES=False)
    
    VOLUME_CONFIRMATION_MULTIPLIER = 1.5   # Reduced from 1.8 for more realistic filtering
    
    PRIMARY_TF = '15m'
    CONTEXT_TF = '1h'
    
    MAX_DAILY_SIGNALS = 80
    MAX_CONCURRENT_SIGNALS = 10  # Increased from 5 to allow more opportunities
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
    
    # Persistence filter: require SUSTAINED reversal before exiting
    # This prevents exits on temporary imbalance spikes (noise)
    IMBALANCE_REVERSAL_PERSISTENCE_SAMPLES = 50  # 50 samples × 100ms = 5 seconds confirmation
    
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'bot/logs/bot.log'
