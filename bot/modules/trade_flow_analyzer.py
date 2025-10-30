"""
Trade Flow Analyzer - analyzes large trades flow (dynamic percentile-based)
Tracks buy/sell pressure from large market orders in 5-minute window
Uses 99th percentile (top 1%) for each symbol instead of fixed threshold
"""
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime, timedelta
import statistics
from bot.config import Config
from bot.utils import logger

class TradeFlowAnalyzer:
    def __init__(self, window_minutes: int = 5):
        self.window_size = window_minutes * 60 * 1000
        self.trades = {}
        self.trade_sizes = {}  # Store trade sizes for percentile calculation
        self.use_dynamic = Config.USE_DYNAMIC_LARGE_TRADES
        self.percentile = Config.LARGE_TRADE_PERCENTILE
        self.min_threshold = Config.MIN_LARGE_TRADE_SIZE
        self.large_trade_size = Config.LARGE_TRADE_SIZE
        
        mode = f"DYNAMIC (top {100-self.percentile}%, min ${self.min_threshold:,.0f})" if self.use_dynamic else f"FIXED (${self.large_trade_size:,.0f})"
        logger.info(f"🔧 [TradeFlowAnalyzer] Initialized with window={window_minutes}min, mode={mode}")
    
    def add_trade(self, symbol: str, trade: Dict):
        try:
            if symbol not in self.trades:
                self.trades[symbol] = deque()
                self.trade_sizes[symbol] = deque()  # Initialize trade sizes tracking
                logger.debug(f"🆕 [TradeFlowAnalyzer] Created new deque for {symbol}")
            
            current_time = trade.get('T', int(datetime.now().timestamp() * 1000))
            
            # Calculate trade size
            try:
                quantity = float(trade.get('q', 0))
                price = float(trade.get('p', 0))
                trade_size = quantity * price
            except (ValueError, TypeError):
                trade_size = 0
            
            # Clean old trades and sizes (BEFORE filtering, preserve indices)
            before_count = len(self.trades[symbol])
            
            # Create parallel lists for filtering
            valid_trades = []
            valid_sizes = []
            for t, s in zip(self.trades[symbol], self.trade_sizes[symbol]):
                if current_time - t.get('T', 0) <= self.window_size:
                    valid_trades.append(t)
                    valid_sizes.append(s)
            
            self.trades[symbol] = deque(valid_trades)
            self.trade_sizes[symbol] = deque(valid_sizes)
            after_count = len(self.trades[symbol])
            
            # Add new trade and size
            self.trades[symbol].append(trade)
            self.trade_sizes[symbol].append(trade_size)
            
            # DIAGNOSTIC: Log accumulation for first few symbols
            if len(self.trades) <= 5 and after_count % 50 == 0:
                logger.info(f"📊 [DIAGNOSTIC] {symbol} - Trades accumulated: {after_count + 1} (cleaned {before_count - after_count})")
            
        except Exception as e:
            logger.error(f"❌ [TradeFlowAnalyzer] Error adding trade for {symbol}: {e}")
    
    def calculate_dynamic_threshold(self, symbol: str) -> float:
        """Calculate dynamic threshold as Nth percentile of trade sizes"""
        try:
            if symbol not in self.trade_sizes or len(self.trade_sizes[symbol]) < 20:
                return self.min_threshold  # Need at least 20 trades for meaningful percentile
            
            sizes = list(self.trade_sizes[symbol])
            threshold = statistics.quantiles(sizes, n=100)[self.percentile - 1]  # 99th percentile
            
            # Apply minimum threshold
            threshold = max(threshold, self.min_threshold)
            
            return threshold
            
        except Exception as e:
            logger.error(f"❌ [TradeFlowAnalyzer] Error calculating threshold for {symbol}: {e}")
            return self.min_threshold
    
    def analyze_trade_flow(self, symbol: str, current_time: Optional[int] = None) -> Dict:
        try:
            # DIAGNOSTIC: Log memory state every 100 calls
            if not hasattr(self, '_analyze_count'):
                self._analyze_count = 0
            self._analyze_count += 1
            if self._analyze_count % 100 == 0:
                logger.debug(f"📊 [DIAGNOSTIC] TradeFlowAnalyzer memory state: {len(self.trades)} symbols tracked, Total trades: {sum(len(deque) for deque in self.trades.values())}")
            
            if symbol not in self.trades or not self.trades[symbol]:
                return {
                    'large_buys': 0,
                    'large_sells': 0,
                    'total_volume': 0,
                    'buy_volume': 0,
                    'sell_volume': 0,
                    'volume_per_minute': 0,
                    'trade_count': 0,
                    'avg_trade_size': 0,
                    'buy_sell_ratio': 0,
                    'dynamic_threshold': 0,
                    'vwap': 0
                }
            
            if current_time is None:
                current_time = int(datetime.now().timestamp() * 1000)
            
            # Clean old trades AND trade_sizes together to keep indices aligned
            valid_trades = []
            valid_sizes = []
            for t, s in zip(self.trades[symbol], self.trade_sizes[symbol]):
                if current_time - t.get('T', 0) <= self.window_size:
                    valid_trades.append(t)
                    valid_sizes.append(s)
            
            self.trades[symbol] = deque(valid_trades)
            self.trade_sizes[symbol] = deque(valid_sizes)
            
            # Determine threshold: dynamic or fixed
            if self.use_dynamic:
                threshold = self.calculate_dynamic_threshold(symbol)
            else:
                threshold = self.large_trade_size
            
            large_buys = 0
            large_sells = 0
            total_volume = 0
            buy_volume = 0
            sell_volume = 0
            trade_sizes = []
            
            # Calculate VWAP = Σ(price * quantity) / Σ(quantity)
            total_pv = 0  # price * volume (quantity)
            total_q = 0   # total quantity
            
            for trade in self.trades[symbol]:
                try:
                    quantity = float(trade.get('q', 0))
                    price = float(trade.get('p', 0))
                    trade_size = quantity * price
                    
                    total_volume += trade_size
                    trade_sizes.append(trade_size)
                    
                    # Add to VWAP calculation
                    total_pv += price * quantity
                    total_q += quantity
                    
                    is_buyer_maker = trade.get('m', False)
                    
                    if is_buyer_maker:
                        sell_volume += trade_size
                        if trade_size >= threshold:
                            large_sells += 1
                            # DIAGNOSTIC: Log large sells (first 5 only)
                            if not hasattr(self, '_large_sell_count'):
                                self._large_sell_count = 0
                            if self._large_sell_count < 5:
                                logger.info(f"💰 [DIAGNOSTIC] LARGE SELL {symbol}: ${trade_size:,.0f} (threshold=${threshold:,.0f}, price=${price:.2f}, qty={quantity:.4f})")
                                self._large_sell_count += 1
                    else:
                        buy_volume += trade_size
                        if trade_size >= threshold:
                            large_buys += 1
                            # DIAGNOSTIC: Log large buys (first 5 only)
                            if not hasattr(self, '_large_buy_count'):
                                self._large_buy_count = 0
                            if self._large_buy_count < 5:
                                logger.info(f"💰 [DIAGNOSTIC] LARGE BUY {symbol}: ${trade_size:,.0f} (threshold=${threshold:,.0f}, price=${price:.2f}, qty={quantity:.4f})")
                                self._large_buy_count += 1
                            
                except Exception as e:
                    logger.error(f"❌ [TradeFlowAnalyzer] Error processing trade: {e}")
                    continue
            
            volume_per_minute = total_volume / (self.window_size / 60000) if self.window_size > 0 else 0
            avg_trade_size = sum(trade_sizes) / len(trade_sizes) if trade_sizes else 0
            buy_sell_ratio = buy_volume / sell_volume if sell_volume > 0 else 0
            
            # Calculate VWAP
            vwap = total_pv / total_q if total_q > 0 else 0
            
            result = {
                'large_buys': large_buys,
                'large_sells': large_sells,
                'total_volume': total_volume,
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'volume_per_minute': volume_per_minute,
                'trade_count': len(self.trades[symbol]),
                'avg_trade_size': avg_trade_size,
                'buy_sell_ratio': buy_sell_ratio,
                'dynamic_threshold': threshold if self.use_dynamic else 0,
                'vwap': vwap  # Real VWAP calculation
            }
            
            # Log for debugging - show volume stats for first few symbols with large trades
            if len(self.trades) <= 10 and large_buys + large_sells > 0:
                logger.info(f"✅ [TradeFlowAnalyzer] {symbol} - Trades: {len(self.trades[symbol])}, Large: B={large_buys}/S={large_sells}, Threshold: ${threshold:,.0f}, Vol/min: ${volume_per_minute:,.0f}")
            
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
                'buy_sell_ratio': 0,
                'dynamic_threshold': 0,
                'vwap': 0
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
