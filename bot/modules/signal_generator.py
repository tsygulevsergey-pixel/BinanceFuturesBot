"""
Signal Generator - generates LONG/SHORT signals based on orderbook imbalance and trade flow
Quality classification: HIGH (80+), MEDIUM (65-79), LOW (50-64)
Scoring: orderbook_imbalance (35 points), volume_confirmation (30 points), large_trades (35 points)
"""
import uuid
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.modules.orderbook_analyzer import orderbook_analyzer
from bot.modules.trade_flow_analyzer import trade_flow_analyzer

class SignalGenerator:
    def __init__(self):
        self.imbalance_threshold = Config.ORDERBOOK_IMBALANCE_THRESHOLD
        self.min_large_trades = Config.MIN_LARGE_TRADES
        self.volume_multiplier = Config.VOLUME_CONFIRMATION_MULTIPLIER
        
        logger.info(f"🔧 [SignalGenerator] Initialized")
    
    def check_long_conditions(
        self,
        orderbook_data: Dict,
        trade_flow: Dict,
        price_data: Dict
    ) -> Tuple[bool, Dict]:
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_buys = trade_flow.get('large_buys', 0)
            volume_intensity = trade_flow.get('volume_intensity', 0)
            price = price_data.get('price', 0)
            vwap = price_data.get('vwap', 0)
            
            required_conditions = {
                'orderbook_imbalance': imbalance > self.imbalance_threshold,
                'large_buy_trades': large_buys >= self.min_large_trades,
                'volume_intensity': volume_intensity > self.volume_multiplier,
                'price_above_vwap': price > vwap if vwap > 0 else True
            }
            
            all_required = all(required_conditions.values())
            
            optional_conditions = {
                'rsi_oversold': price_data.get('rsi', 50) < 30,
                'support_level': price_data.get('near_support', False)
            }
            
            return all_required, {
                'required': required_conditions,
                'optional': optional_conditions
            }
            
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error checking LONG conditions: {e}")
            return False, {}
    
    def check_short_conditions(
        self,
        orderbook_data: Dict,
        trade_flow: Dict,
        price_data: Dict
    ) -> Tuple[bool, Dict]:
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_sells = trade_flow.get('large_sells', 0)
            volume_intensity = trade_flow.get('volume_intensity', 0)
            price = price_data.get('price', 0)
            vwap = price_data.get('vwap', 0)
            
            required_conditions = {
                'orderbook_imbalance': imbalance < -self.imbalance_threshold,
                'large_sell_trades': large_sells >= self.min_large_trades,
                'volume_intensity': volume_intensity > self.volume_multiplier,
                'price_below_vwap': price < vwap if vwap > 0 else True
            }
            
            all_required = all(required_conditions.values())
            
            optional_conditions = {
                'rsi_overbought': price_data.get('rsi', 50) > 70,
                'resistance_level': price_data.get('near_resistance', False)
            }
            
            return all_required, {
                'required': required_conditions,
                'optional': optional_conditions
            }
            
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error checking SHORT conditions: {e}")
            return False, {}
    
    def calculate_signal_quality(self, signal_data: Dict) -> Tuple[str, float]:
        try:
            quality_score = 0
            
            imbalance = abs(signal_data.get('orderbook_imbalance', 0))
            if imbalance > 0.4:
                quality_score += 35
            elif imbalance > 0.3:
                quality_score += 25
            else:
                quality_score += 15
            
            volume_intensity = signal_data.get('volume_intensity', 0)
            if volume_intensity >= 2.0:
                quality_score += 30
            elif volume_intensity >= 1.5:
                quality_score += 20
            else:
                quality_score += 10
            
            large_trades = max(
                signal_data.get('large_buys', 0),
                signal_data.get('large_sells', 0)
            )
            quality_score += min(large_trades * 8, 35)
            
            if quality_score >= 80:
                return 'HIGH', quality_score
            elif quality_score >= 65:
                return 'MEDIUM', quality_score
            else:
                return 'LOW', quality_score
                
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error calculating signal quality: {e}")
            return 'LOW', 50.0
    
    def generate_signal(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        orderbook_data: Dict,
        trade_flow: Dict,
        price_data: Dict
    ) -> Optional[Dict]:
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_buys = trade_flow.get('large_buys', 0)
            large_sells = trade_flow.get('large_sells', 0)
            volume_intensity = trade_flow.get('volume_per_minute', 0) / 1_000_000
            
            signal_data = {
                'orderbook_imbalance': imbalance,
                'large_buys': large_buys,
                'large_sells': large_sells,
                'volume_intensity': volume_intensity
            }
            
            priority, quality_score = self.calculate_signal_quality(signal_data)
            
            if direction == 'LONG':
                stop_loss = entry_price * 0.98
                take_profit_1 = entry_price * 1.02
                take_profit_2 = entry_price * 1.03
            else:
                stop_loss = entry_price * 1.02
                take_profit_1 = entry_price * 0.98
                take_profit_2 = entry_price * 0.97
            
            risk = abs(entry_price - stop_loss) / entry_price
            reward_tp1 = abs(take_profit_1 - entry_price) / entry_price
            reward_tp2 = abs(take_profit_2 - entry_price) / entry_price
            
            rr_ratio = reward_tp1 / risk if risk > 0 else 0
            
            priority_config = Config.PRIORITY_LEVELS.get(priority, Config.PRIORITY_LEVELS['LOW'])
            hold_time_min = priority_config['hold_time_min']
            hold_time_max = priority_config['hold_time_max']
            expected_hold_time = f"{hold_time_min}-{hold_time_max}min"
            
            confidence = min((quality_score / 100) * (1 + abs(imbalance)), 1.0)
            
            signal = {
                'signal_id': str(uuid.uuid4()),
                'symbol': symbol,
                'direction': direction,
                'signal_type': 'ENTRY',
                'priority': priority,
                'timestamp': datetime.now().isoformat(),
                
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                
                'quality_score': quality_score,
                'orderbook_imbalance': imbalance,
                'large_trades_count': large_buys if direction == 'LONG' else large_sells,
                'volume_intensity': volume_intensity,
                'confidence': confidence,
                
                'suggested_position_size': 0.01,
                'risk_reward_ratio': rr_ratio,
                'expected_hold_time': expected_hold_time
            }
            
            logger.info(
                f"🎯 [SignalGenerator] Generated {priority} {direction} signal for {symbol} @ ${entry_price:.4f} "
                f"(Quality: {quality_score:.1f}, Imbalance: {imbalance:.3f}, Confidence: {confidence:.2f})"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error generating signal for {symbol}: {e}")
            return None

signal_generator = SignalGenerator()
