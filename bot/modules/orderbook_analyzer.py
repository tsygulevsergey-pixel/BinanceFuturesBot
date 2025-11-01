"""
OrderBook Analyzer - analyzes order book imbalance and large orders
Detects: imbalance >0.28, large orders (>5x average size)
"""
from typing import Dict, List, Optional, Tuple
from bot.config import Config
from bot.utils import logger
import numpy as np

class OrderBookAnalyzer:
    def __init__(self):
        self.imbalance_threshold = Config.ORDERBOOK_IMBALANCE_THRESHOLD
        logger.info(f"🔧 [OrderBookAnalyzer] Initialized with imbalance threshold={self.imbalance_threshold}")
    
    def calculate_imbalance(self, bids: List, asks: List, depth: int = 200) -> float:
        try:
            if not bids or not asks:
                return 0.0
            
            bid_volume = sum(float(bid[1]) for bid in bids[:depth])
            ask_volume = sum(float(ask[1]) for ask in asks[:depth])
            
            if bid_volume + ask_volume == 0:
                return 0.0
            
            imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
            
            logger.debug(f"📊 [OrderBookAnalyzer] Imbalance calculated: {imbalance:.4f} (bids={bid_volume:.2f}, asks={ask_volume:.2f})")
            
            return imbalance
            
        except Exception as e:
            logger.error(f"❌ [OrderBookAnalyzer] Error calculating imbalance: {e}")
            return 0.0
    
    def detect_large_orders(
        self,
        orderbook: Dict,
        side: str = 'both'
    ) -> List[Dict]:
        try:
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                return []
            
            all_volumes = []
            if side in ['bids', 'both']:
                all_volumes.extend([float(b[1]) for b in bids])
            if side in ['asks', 'both']:
                all_volumes.extend([float(a[1]) for a in asks])
            
            if not all_volumes:
                return []
            
            avg_size = np.mean(all_volumes)
            threshold = avg_size * 5
            
            large_orders = []
            
            if side in ['bids', 'both']:
                for price, volume in bids:
                    volume_float = float(volume)
                    if volume_float > threshold:
                        large_orders.append({
                            'side': 'bid',
                            'price': float(price),
                            'volume': volume_float,
                            'size_multiple': volume_float / avg_size
                        })
            
            if side in ['asks', 'both']:
                for price, volume in asks:
                    volume_float = float(volume)
                    if volume_float > threshold:
                        large_orders.append({
                            'side': 'ask',
                            'price': float(price),
                            'volume': volume_float,
                            'size_multiple': volume_float / avg_size
                        })
            
            if large_orders:
                logger.debug(f"🔍 [OrderBookAnalyzer] Detected {len(large_orders)} large orders (threshold={threshold:.2f}, avg={avg_size:.2f})")
            
            return large_orders
            
        except Exception as e:
            logger.error(f"❌ [OrderBookAnalyzer] Error detecting large orders: {e}")
            return []
    
    def analyze_orderbook_depth(self, orderbook: Dict, price: float) -> Dict:
        try:
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                return {
                    'bid_depth_1pct': 0,
                    'ask_depth_1pct': 0,
                    'total_depth_1pct': 0,
                    'depth_ratio': 0
                }
            
            depth_threshold = price * 0.01
            
            bid_depth = sum(
                float(b[0]) * float(b[1])
                for b in bids
                if price - float(b[0]) <= depth_threshold
            )
            
            ask_depth = sum(
                float(a[0]) * float(a[1])
                for a in asks
                if float(a[0]) - price <= depth_threshold
            )
            
            total_depth = bid_depth + ask_depth
            depth_ratio = bid_depth / ask_depth if ask_depth > 0 else 0
            
            return {
                'bid_depth_1pct': bid_depth,
                'ask_depth_1pct': ask_depth,
                'total_depth_1pct': total_depth,
                'depth_ratio': depth_ratio
            }
            
        except Exception as e:
            logger.error(f"❌ [OrderBookAnalyzer] Error analyzing orderbook depth: {e}")
            return {
                'bid_depth_1pct': 0,
                'ask_depth_1pct': 0,
                'total_depth_1pct': 0,
                'depth_ratio': 0
            }
    
    def get_spread(self, orderbook: Dict) -> float:
        try:
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                return 0.0
            
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            
            if best_bid == 0:
                return 0.0
            
            spread = (best_ask - best_bid) / best_bid
            
            return spread
            
        except Exception as e:
            logger.error(f"❌ [OrderBookAnalyzer] Error calculating spread: {e}")
            return 0.0

orderbook_analyzer = OrderBookAnalyzer()
