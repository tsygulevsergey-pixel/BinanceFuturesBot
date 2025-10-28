"""
Trade Flow Analyzer - analyzes large trades flow (>$50k)
Tracks buy/sell pressure from large market orders in 5-minute window
"""
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger

class TradeFlowAnalyzer:
    def __init__(self, window_minutes: int = 5):
        self.window_size = window_minutes * 60 * 1000
        self.trades = {}
        self.large_trade_size = Config.LARGE_TRADE_SIZE
        
        logger.info(f"🔧 [TradeFlowAnalyzer] Initialized with window={window_minutes}min, large_trade_size=${self.large_trade_size}")
    
    def add_trade(self, symbol: str, trade: Dict):
        try:
            if symbol not in self.trades:
                self.trades[symbol] = deque()
            
            current_time = trade.get('T', int(datetime.now().timestamp() * 1000))
            
            self.trades[symbol] = deque([
                t for t in self.trades[symbol]
                if current_time - t.get('T', 0) <= self.window_size
            ])
            
            self.trades[symbol].append(trade)
            
        except Exception as e:
            logger.error(f"❌ [TradeFlowAnalyzer] Error adding trade for {symbol}: {e}")
    
    def analyze_trade_flow(self, symbol: str, current_time: Optional[int] = None) -> Dict:
        try:
            if symbol not in self.trades or not self.trades[symbol]:
                # Log first 5 symbols to understand why no trades
                if len(self.trades) < 5 or symbol not in list(self.trades.keys())[:5]:
                    logger.debug(f"⚠️ [TradeFlowAnalyzer] {symbol} - No trades in memory (total symbols tracked: {len(self.trades)})")
                return {
                    'large_buys': 0,
                    'large_sells': 0,
                    'total_volume': 0,
                    'buy_volume': 0,
                    'sell_volume': 0,
                    'volume_per_minute': 0,
                    'trade_count': 0,
                    'avg_trade_size': 0,
                    'buy_sell_ratio': 0
                }
            
            if current_time is None:
                current_time = int(datetime.now().timestamp() * 1000)
            
            self.trades[symbol] = deque([
                t for t in self.trades[symbol]
                if current_time - t.get('T', 0) <= self.window_size
            ])
            
            large_buys = 0
            large_sells = 0
            total_volume = 0
            buy_volume = 0
            sell_volume = 0
            trade_sizes = []
            
            for trade in self.trades[symbol]:
                try:
                    quantity = float(trade.get('q', 0))
                    price = float(trade.get('p', 0))
                    trade_size = quantity * price
                    
                    total_volume += trade_size
                    trade_sizes.append(trade_size)
                    
                    is_buyer_maker = trade.get('m', False)
                    
                    if is_buyer_maker:
                        sell_volume += trade_size
                        if trade_size >= self.large_trade_size:
                            large_sells += 1
                    else:
                        buy_volume += trade_size
                        if trade_size >= self.large_trade_size:
                            large_buys += 1
                            
                except Exception as e:
                    logger.error(f"❌ [TradeFlowAnalyzer] Error processing trade: {e}")
                    continue
            
            volume_per_minute = total_volume / (self.window_size / 60000) if self.window_size > 0 else 0
            avg_trade_size = sum(trade_sizes) / len(trade_sizes) if trade_sizes else 0
            buy_sell_ratio = buy_volume / sell_volume if sell_volume > 0 else 0
            
            result = {
                'large_buys': large_buys,
                'large_sells': large_sells,
                'total_volume': total_volume,
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'volume_per_minute': volume_per_minute,
                'trade_count': len(self.trades[symbol]),
                'avg_trade_size': avg_trade_size,
                'buy_sell_ratio': buy_sell_ratio
            }
            
            # Log for debugging - show volume stats for first few symbols
            if len(self.trades) <= 10 and large_buys + large_sells > 0:
                logger.info(f"✅ [TradeFlowAnalyzer] {symbol} - Trades: {len(self.trades[symbol])}, Large: B={large_buys}/S={large_sells}, Vol/min: ${volume_per_minute:,.0f}, Avg: ${avg_trade_size:,.0f}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ [TradeFlowAnalyzer] Error analyzing trade flow for {symbol}: {e}")
            return {
                'large_buys': 0,
                'large_sells': 0,
                'total_volume': 0,
                'buy_volume': 0,
                'sell_volume': 0,
                'volume_per_minute': 0,
                'trade_count': 0,
                'avg_trade_size': 0,
                'buy_sell_ratio': 0
            }
    
    def clear_old_trades(self, symbol: str, current_time: Optional[int] = None):
        try:
            if symbol not in self.trades:
                return
            
            if current_time is None:
                current_time = int(datetime.now().timestamp() * 1000)
            
            before_count = len(self.trades[symbol])
            
            self.trades[symbol] = deque([
                t for t in self.trades[symbol]
                if current_time - t.get('T', 0) <= self.window_size
            ])
            
            after_count = len(self.trades[symbol])
            
            if before_count != after_count:
                logger.debug(f"🗑️ [TradeFlowAnalyzer] Cleared {before_count - after_count} old trades for {symbol}")
                
        except Exception as e:
            logger.error(f"❌ [TradeFlowAnalyzer] Error clearing old trades for {symbol}: {e}")

trade_flow_analyzer = TradeFlowAnalyzer()
