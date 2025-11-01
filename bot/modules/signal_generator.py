"""
Signal Generator - generates LONG/SHORT signals based on orderbook imbalance and trade flow
NOW WITH DYNAMIC SL/TP based on orderbook levels and volatility

Quality classification: HIGH (80+), MEDIUM (65-79), LOW (50-64)
Scoring: 
  - Orderbook imbalance (35 points): ≥0.35→35pts, >0.30→25pts, ≤0.30→15pts
  - Volume confirmation (30 points): ≥2.0x→30pts, ≥1.5x→20pts, <1.5x→10pts
  - Large trades (35 points): 8 points per large trade (max 35)

Minimum entry requirements:
  - imbalance ≥ 0.25
  - large_trades ≥ 2
  - volume ≥ 1.5x average
"""
import uuid
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.modules.orderbook_analyzer import orderbook_analyzer
from bot.modules.trade_flow_analyzer import trade_flow_analyzer
from bot.modules.volatility_calculator import VolatilityCalculator
from bot.modules.orderbook_levels_analyzer import OrderbookLevelsAnalyzer
from bot.modules.dynamic_stop_loss_finder import DynamicStopLossFinder
from bot.modules.dynamic_take_profit_finder import DynamicTakeProfitFinder
from bot.modules.signal_validator import SignalValidator

class SignalGenerator:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.imbalance_threshold = Config.ORDERBOOK_IMBALANCE_THRESHOLD
        self.min_large_trades = Config.MIN_LARGE_TRADES
        self.volume_multiplier = Config.VOLUME_CONFIRMATION_MULTIPLIER
        
        # Initialize dynamic SL/TP modules
        self.volatility_calc = VolatilityCalculator(db_pool)
        self.levels_analyzer = OrderbookLevelsAnalyzer(db_pool)
        self.stop_finder = DynamicStopLossFinder()
        self.tp_finder = DynamicTakeProfitFinder()
        self.validator = SignalValidator(Config.__dict__)
        
        logger.info(f"🔧 [SignalGenerator] Initialized with dynamic SL/TP modules")
    
    def quick_check_long(self, orderbook_data: Dict, trade_flow: Dict) -> bool:
        """Quick pre-check: only imbalance and large_trades (no API calls needed)"""
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_buys = trade_flow.get('large_buys', 0)
            
            return (imbalance >= self.imbalance_threshold and 
                    large_buys >= self.min_large_trades)
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error in quick_check_long: {e}")
            return False
    
    def quick_check_short(self, orderbook_data: Dict, trade_flow: Dict) -> bool:
        """Quick pre-check: only imbalance and large_trades (no API calls needed)"""
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_sells = trade_flow.get('large_sells', 0)
            
            return (imbalance <= -self.imbalance_threshold and 
                    large_sells >= self.min_large_trades)
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error in quick_check_short: {e}")
            return False
    
    async def check_long_conditions(
        self,
        symbol: str,
        orderbook_data: Dict,
        trade_flow: Dict,
        price_data: Dict,
        orderbook_snapshot: Dict
    ) -> Tuple[bool, Dict]:
        """
        Check LONG conditions with dynamic SL/TP calculation
        
        Returns:
            (is_valid, data_dict) where data_dict contains:
            - required/optional conditions
            - stop_loss info
            - take_profit info
            - levels analysis
            - validation results
        """
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_buys = trade_flow.get('large_buys', 0)
            volume_intensity = trade_flow.get('volume_intensity', 0)
            price = price_data.get('price', 0)
            vwap = price_data.get('vwap', 0)
            
            required_conditions = {
                'orderbook_imbalance': imbalance >= self.imbalance_threshold,
                'large_buy_trades': large_buys >= self.min_large_trades,
                'volume_intensity': volume_intensity >= self.volume_multiplier,
                'price_above_vwap': price > vwap if vwap > 0 else True
            }
            
            all_required = all(required_conditions.values())
            
            optional_conditions = {
                'rsi_oversold': price_data.get('rsi', 50) < 30,
                'support_level': price_data.get('near_support', False)
            }
            
            # If basic conditions don't pass, return early
            if not all_required:
                return False, {
                    'required': required_conditions,
                    'optional': optional_conditions
                }
            
            logger.info(f"📊 [SignalGenerator] Basic LONG conditions passed for {symbol}, calculating dynamic SL/TP...")
            
            # === DYNAMIC SL/TP CALCULATION ===
            try:
                # Calculate volatility and working range
                volatility = await self.volatility_calc.calculate_atr(symbol)
                if not volatility:
                    logger.warning(f"⚠️ [SignalGenerator] Could not calculate volatility for {symbol}")
                    return False, {'error': 'No volatility data'}
                
                working_range = await self.volatility_calc.get_working_range(symbol)
                if not working_range:
                    logger.warning(f"⚠️ [SignalGenerator] Could not calculate working range for {symbol}")
                    return False, {'error': 'No working range data'}
                
                logger.info(f"   ✓ Volatility: {volatility['category']} (ATR: {volatility['atr']:.8f}, {volatility['volatility_pct']:.2f}%)")
                
                # Analyze orderbook levels
                levels = await self.levels_analyzer.analyze(
                    symbol, price, working_range, orderbook_snapshot
                )
                if not levels:
                    logger.warning(f"⚠️ [SignalGenerator] Could not analyze levels for {symbol}")
                    return False, {'error': 'No levels data'}
                
                logger.info(f"   ✓ Levels: {len(levels.get('support_levels', []))} support, {len(levels.get('resistance_levels', []))} resistance")
                
                # Find dynamic stop loss
                stop_info = self.stop_finder.find_stop_for_long(
                    price, levels, volatility
                )
                if not stop_info or not stop_info.get('is_valid'):
                    logger.warning(f"⚠️ [SignalGenerator] Invalid stop for {symbol}: {stop_info.get('reason') if stop_info else 'unknown'}")
                    return False, {'error': 'Invalid stop loss', 'stop_info': stop_info}
                
                logger.info(f"   ✓ Stop: ${stop_info['stop_loss_price']:.4f} ({stop_info['stop_distance_pct']:.2f}% away)")
                
                # Find dynamic take profits
                tp_info = self.tp_finder.find_targets_for_long(
                    price, stop_info, levels
                )
                if not tp_info or not tp_info.get('is_valid'):
                    logger.warning(f"⚠️ [SignalGenerator] Invalid targets for {symbol}: {tp_info.get('reason') if tp_info else 'unknown'}")
                    return False, {'error': 'Invalid take profit', 'tp_info': tp_info}
                
                logger.info(f"   ✓ TP1: ${tp_info['tp1_price']:.4f} (R/R: {tp_info['tp1_rr']:.2f})")
                logger.info(f"   ✓ TP2: ${tp_info['tp2_price']:.4f} (R/R: {tp_info['tp2_rr']:.2f})")
                
                # Validate signal
                validation = self.validator.validate(
                    imbalance, large_buys, volume_intensity,
                    stop_info, tp_info, levels
                )
                
                logger.info(f"   ✓ Validation: {'PASSED' if validation['is_valid'] else 'FAILED'} - {validation['priority']} priority (score: {validation['quality_score']:.1f})")
                
                if not validation['is_valid']:
                    logger.warning(f"⚠️ [SignalGenerator] Signal validation failed for {symbol}")
                    for reason in validation.get('rejection_reasons', []):
                        logger.warning(f"      - {reason}")
                
                # Return validation result + all data
                return validation['is_valid'], {
                    'required': required_conditions,
                    'optional': optional_conditions,
                    'stop_loss': stop_info,
                    'take_profit': tp_info,
                    'levels': levels,
                    'validation': validation,
                    'volatility': volatility,
                    'working_range': working_range
                }
                
            except Exception as e:
                logger.error(f"❌ [SignalGenerator] Error in dynamic SL/TP calculation for {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False, {'error': str(e)}
            
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error checking LONG conditions: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, {}
    
    async def check_short_conditions(
        self,
        symbol: str,
        orderbook_data: Dict,
        trade_flow: Dict,
        price_data: Dict,
        orderbook_snapshot: Dict
    ) -> Tuple[bool, Dict]:
        """
        Check SHORT conditions with dynamic SL/TP calculation
        
        Returns:
            (is_valid, data_dict) where data_dict contains:
            - required/optional conditions
            - stop_loss info
            - take_profit info
            - levels analysis
            - validation results
        """
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_sells = trade_flow.get('large_sells', 0)
            volume_intensity = trade_flow.get('volume_intensity', 0)
            price = price_data.get('price', 0)
            vwap = price_data.get('vwap', 0)
            
            required_conditions = {
                'orderbook_imbalance': imbalance <= -self.imbalance_threshold,
                'large_sell_trades': large_sells >= self.min_large_trades,
                'volume_intensity': volume_intensity >= self.volume_multiplier,
                'price_below_vwap': price < vwap if vwap > 0 else True
            }
            
            all_required = all(required_conditions.values())
            
            optional_conditions = {
                'rsi_overbought': price_data.get('rsi', 50) > 70,
                'resistance_level': price_data.get('near_resistance', False)
            }
            
            # If basic conditions don't pass, return early
            if not all_required:
                return False, {
                    'required': required_conditions,
                    'optional': optional_conditions
                }
            
            logger.info(f"📊 [SignalGenerator] Basic SHORT conditions passed for {symbol}, calculating dynamic SL/TP...")
            
            # === DYNAMIC SL/TP CALCULATION ===
            try:
                # Calculate volatility and working range
                volatility = await self.volatility_calc.calculate_atr(symbol)
                if not volatility:
                    logger.warning(f"⚠️ [SignalGenerator] Could not calculate volatility for {symbol}")
                    return False, {'error': 'No volatility data'}
                
                working_range = await self.volatility_calc.get_working_range(symbol)
                if not working_range:
                    logger.warning(f"⚠️ [SignalGenerator] Could not calculate working range for {symbol}")
                    return False, {'error': 'No working range data'}
                
                logger.info(f"   ✓ Volatility: {volatility['category']} (ATR: {volatility['atr']:.8f}, {volatility['volatility_pct']:.2f}%)")
                
                # Analyze orderbook levels
                levels = await self.levels_analyzer.analyze(
                    symbol, price, working_range, orderbook_snapshot
                )
                if not levels:
                    logger.warning(f"⚠️ [SignalGenerator] Could not analyze levels for {symbol}")
                    return False, {'error': 'No levels data'}
                
                logger.info(f"   ✓ Levels: {len(levels.get('support_levels', []))} support, {len(levels.get('resistance_levels', []))} resistance")
                
                # Find dynamic stop loss for SHORT
                stop_info = self.stop_finder.find_stop_for_short(
                    price, levels, volatility
                )
                if not stop_info or not stop_info.get('is_valid'):
                    logger.warning(f"⚠️ [SignalGenerator] Invalid stop for {symbol}: {stop_info.get('reason') if stop_info else 'unknown'}")
                    return False, {'error': 'Invalid stop loss', 'stop_info': stop_info}
                
                logger.info(f"   ✓ Stop: ${stop_info['stop_loss_price']:.4f} ({stop_info['stop_distance_pct']:.2f}% away)")
                
                # Find dynamic take profits for SHORT
                tp_info = self.tp_finder.find_targets_for_short(
                    price, stop_info, levels
                )
                if not tp_info or not tp_info.get('is_valid'):
                    logger.warning(f"⚠️ [SignalGenerator] Invalid targets for {symbol}: {tp_info.get('reason') if tp_info else 'unknown'}")
                    return False, {'error': 'Invalid take profit', 'tp_info': tp_info}
                
                logger.info(f"   ✓ TP1: ${tp_info['tp1_price']:.4f} (R/R: {tp_info['tp1_rr']:.2f})")
                logger.info(f"   ✓ TP2: ${tp_info['tp2_price']:.4f} (R/R: {tp_info['tp2_rr']:.2f})")
                
                # Validate signal
                validation = self.validator.validate(
                    imbalance, large_sells, volume_intensity,
                    stop_info, tp_info, levels
                )
                
                logger.info(f"   ✓ Validation: {'PASSED' if validation['is_valid'] else 'FAILED'} - {validation['priority']} priority (score: {validation['quality_score']:.1f})")
                
                if not validation['is_valid']:
                    logger.warning(f"⚠️ [SignalGenerator] Signal validation failed for {symbol}")
                    for reason in validation.get('rejection_reasons', []):
                        logger.warning(f"      - {reason}")
                
                # Return validation result + all data
                return validation['is_valid'], {
                    'required': required_conditions,
                    'optional': optional_conditions,
                    'stop_loss': stop_info,
                    'take_profit': tp_info,
                    'levels': levels,
                    'validation': validation,
                    'volatility': volatility,
                    'working_range': working_range
                }
                
            except Exception as e:
                logger.error(f"❌ [SignalGenerator] Error in dynamic SL/TP calculation for {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False, {'error': str(e)}
            
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error checking SHORT conditions: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, {}
    
    def calculate_signal_quality(self, signal_data: Dict) -> Tuple[str, float]:
        try:
            quality_score = 0
            
            imbalance = abs(signal_data.get('orderbook_imbalance', 0))
            if imbalance >= 0.35:
                quality_score += 35
            elif imbalance > 0.30:
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
        price_data: Dict,
        dynamic_data: Dict
    ) -> Optional[Dict]:
        """
        Generate signal with dynamic SL/TP levels
        
        Args:
            symbol: Trading symbol
            direction: LONG or SHORT
            entry_price: Entry price
            orderbook_data: Orderbook analysis
            trade_flow: Trade flow analysis
            price_data: Price data
            dynamic_data: Dynamic SL/TP data from check_conditions
        """
        try:
            imbalance = orderbook_data.get('imbalance', 0)
            large_buys = trade_flow.get('large_buys', 0)
            large_sells = trade_flow.get('large_sells', 0)
            volume_intensity = trade_flow.get('volume_intensity', 0)
            
            # Extract dynamic SL/TP data
            stop_info = dynamic_data.get('stop_loss', {})
            tp_info = dynamic_data.get('take_profit', {})
            validation = dynamic_data.get('validation', {})
            levels = dynamic_data.get('levels', {})
            volatility = dynamic_data.get('volatility', {})
            
            # Use validation priority and quality score (already calculated)
            priority = validation.get('priority', 'MEDIUM')
            quality_score = validation.get('quality_score', 50.0)
            
            # Extract dynamic prices
            stop_loss_price = stop_info.get('stop_loss_price')
            stop_loss_reason = stop_info.get('reason', 'Unknown')
            take_profit_1 = tp_info.get('tp1_price')
            take_profit_2 = tp_info.get('tp2_price')
            tp1_reason = tp_info.get('tp1_reason', 'Unknown')
            tp2_reason = tp_info.get('tp2_reason', 'Unknown')
            rr_ratio = tp_info.get('tp1_rr', 0)
            
            # Get level info based on direction
            support_level = stop_info.get('support_level') if direction == 'LONG' else None
            resistance_level = stop_info.get('resistance_level') if direction == 'SHORT' else None
            
            # Calculate expected hold time based on priority
            priority_config = Config.PRIORITY_LEVELS.get(priority, Config.PRIORITY_LEVELS['LOW'])
            hold_time_min = priority_config['hold_time_min']
            hold_time_max = priority_config['hold_time_max']
            expected_hold_time = f"{hold_time_min}-{hold_time_max}min"
            
            # Calculate confidence
            confidence = min((quality_score / 100) * (1 + abs(imbalance)), 1.0)
            
            # Build signal with dynamic data
            signal = {
                'signal_id': str(uuid.uuid4()),
                'symbol': symbol,
                'direction': direction,
                'signal_type': 'ENTRY',
                'priority': priority,
                'timestamp': datetime.now().isoformat(),
                
                # Entry and exit prices (DYNAMIC)
                'entry_price': entry_price,
                'stop_loss': stop_loss_price,
                'stop_loss_price': stop_loss_price,
                'stop_loss_reason': stop_loss_reason,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                'tp1_reason': tp1_reason,
                'tp2_reason': tp2_reason,
                
                # Quality metrics
                'quality_score': quality_score,
                'orderbook_imbalance': imbalance,
                'large_trades_count': large_buys if direction == 'LONG' else large_sells,
                'volume_intensity': volume_intensity,
                'confidence': confidence,
                'risk_reward_ratio': rr_ratio,
                
                # Level information
                'support_level': support_level,
                'resistance_level': resistance_level,
                'total_levels_found': levels.get('total_levels_found', 0),
                
                # Volatility info
                'volatility_category': volatility.get('category', 'UNKNOWN'),
                'atr': volatility.get('atr'),
                'volatility_pct': volatility.get('volatility_pct'),
                
                # Stop/TP distances
                'stop_distance_pct': stop_info.get('stop_distance_pct'),
                'tp1_distance_pct': tp_info.get('tp1_distance_pct'),
                'tp2_distance_pct': tp_info.get('tp2_distance_pct'),
                'tp2_rr': tp_info.get('tp2_rr'),
                
                # Position sizing and hold time
                'suggested_position_size': 0.01,
                'expected_hold_time': expected_hold_time,
                
                # Validation warnings (if any)
                'warnings': validation.get('warnings', [])
            }
            
            logger.info(
                f"🎯 [SignalGenerator] Generated {priority} {direction} signal for {symbol} @ ${entry_price:.4f}"
            )
            logger.info(
                f"   Quality: {quality_score:.1f}, R/R: {rr_ratio:.2f}, "
                f"SL: ${stop_loss_price:.4f} ({stop_info.get('stop_distance_pct', 0):.2f}%), "
                f"TP1: ${take_profit_1:.4f} ({tp_info.get('tp1_distance_pct', 0):.2f}%)"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ [SignalGenerator] Error generating signal for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

# NOTE: SignalGenerator now requires db_pool parameter
# Module-level instance should be created in main.py or wherever db_pool is available
# Example: signal_generator = SignalGenerator(db_pool)
