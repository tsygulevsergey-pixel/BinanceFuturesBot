"""
Risk Manager - manages correlation checks and prevents duplicate symbols
Limits: NO daily/concurrent limits (removed per user request)
Correlation filter: Active (prevents duplicate symbols and high correlation)
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.database import db_manager, Signal
import numpy as np

class RiskManager:
    def __init__(self):
        self.max_daily_signals = Config.MAX_DAILY_SIGNALS
        self.max_concurrent_signals = Config.MAX_CONCURRENT_SIGNALS
        self.correlation_threshold = Config.CORRELATION_THRESHOLD
        self.priority_limits = Config.PRIORITY_LEVELS
        
        logger.info(
            f"🔧 [RiskManager] Initialized - "
            f"Daily limit: {self.max_daily_signals}, "
            f"Concurrent limit: {self.max_concurrent_signals}, "
            f"Correlation threshold: {self.correlation_threshold}"
        )
    
    def can_send_signal(self, symbol: str, priority: str) -> Tuple[bool, str]:
        try:
            # Daily and concurrent limits removed (set to 999999)
            # Only correlation check remains active
            
            with db_manager.get_session() as session:
                if not self.check_correlation(symbol, session):
                    logger.warning(f"⛔ [RiskManager] Correlation check failed for {symbol}")
                    return False, f"High correlation with existing signals"
                
                logger.debug(f"✅ [RiskManager] Signal approved - Correlation check passed")
                
                return True, "Approved"
                
        except Exception as e:
            logger.error(f"❌ [RiskManager] Error checking signal approval: {e}")
            return False, f"Error: {str(e)}"
    
    def check_correlation(self, new_symbol: str, session) -> bool:
        try:
            active_signals = session.query(Signal).filter(
                Signal.status == 'OPEN'
            ).all()
            
            if not active_signals:
                return True
            
            active_symbols = [s.symbol for s in active_signals]
            
            if new_symbol in active_symbols:
                logger.debug(f"⚠️ [RiskManager] Symbol {new_symbol} already has active signal")
                return False
            
            correlation_count = 0
            for symbol in active_symbols:
                if self._calculate_correlation(new_symbol, symbol) > self.correlation_threshold:
                    correlation_count += 1
            
            if correlation_count > len(active_symbols) * 0.5:
                logger.warning(f"⚠️ [RiskManager] High correlation detected for {new_symbol}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [RiskManager] Error checking correlation: {e}")
            return True
    
    def _calculate_correlation(self, symbol1: str, symbol2: str) -> float:
        try:
            base1 = symbol1.replace('USDT', '')
            base2 = symbol2.replace('USDT', '')
            
            if base1 == base2:
                return 1.0
            
            major_coins = ['BTC', 'ETH', 'BNB']
            if base1 in major_coins and base2 in major_coins:
                return 0.7
            
            if base1 in major_coins or base2 in major_coins:
                return 0.3
            
            return 0.1
            
        except Exception as e:
            logger.error(f"❌ [RiskManager] Error calculating correlation: {e}")
            return 0.0
    
    def get_daily_stats(self) -> Dict:
        try:
            today = datetime.now().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            with db_manager.get_session() as session:
                total_signals = session.query(Signal).filter(
                    Signal.created_at >= today_start
                ).count()
                
                high_signals = session.query(Signal).filter(
                    Signal.created_at >= today_start,
                    Signal.priority == 'HIGH'
                ).count()
                
                medium_signals = session.query(Signal).filter(
                    Signal.created_at >= today_start,
                    Signal.priority == 'MEDIUM'
                ).count()
                
                low_signals = session.query(Signal).filter(
                    Signal.created_at >= today_start,
                    Signal.priority == 'LOW'
                ).count()
                
                concurrent_signals = session.query(Signal).filter(
                    Signal.status == 'OPEN'
                ).count()
                
                stats = {
                    'total_today': total_signals,
                    'high_priority': high_signals,
                    'medium_priority': medium_signals,
                    'low_priority': low_signals,
                    'concurrent_open': concurrent_signals,
                    'limits': {
                        'total': self.max_daily_signals,
                        'concurrent': self.max_concurrent_signals,
                        'high': self.priority_limits['HIGH']['max_daily'],
                        'medium': self.priority_limits['MEDIUM']['max_daily'],
                        'low': self.priority_limits['LOW']['max_daily']
                    }
                }
                
                return stats
                
        except Exception as e:
            logger.error(f"❌ [RiskManager] Error getting daily stats: {e}")
            return {}

risk_manager = RiskManager()
