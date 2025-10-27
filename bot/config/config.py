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
    
    UNIVERSE_RESCAN_INTERVAL = 6 * 3600
    MIN_24H_VOLUME = 50_000_000
    MIN_OPEN_INTEREST = 10_000_000
    MAX_SPREAD = 0.0002
    
    ORDERBOOK_IMBALANCE_THRESHOLD = 0.28
    MIN_LARGE_TRADES = 3
    LARGE_TRADE_SIZE = 50_000
    VOLUME_CONFIRMATION_MULTIPLIER = 1.8
    
    PRIMARY_TF = '15m'
    CONTEXT_TF = '1h'
    
    MAX_DAILY_SIGNALS = 80
    MAX_CONCURRENT_SIGNALS = 5
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
    
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'bot/logs/bot.log'
