"""
Dynamic Take Profit Finder - размещение TP на рыночных уровнях
TP1 на ближайшем уровне, TP2 на следующем, с проверкой R/R
"""

from typing import Dict, Optional


class DynamicTakeProfitFinder:
    """
    Находит оптимальные уровни тейк-профита на основе
    реальных уровней сопротивления/поддержки из стакана
    """
    
    def __init__(self, min_tp_distance_pct: float = 0.20, min_rr_ratio: float = 0.8):
        """
        Args:
            min_tp_distance_pct: Минимальное расстояние TP от входа в % (защита от комиссий)
            min_rr_ratio: Минимальный Risk/Reward ratio для принятия сигнала
        """
        self.min_tp_distance_pct = min_tp_distance_pct
        self.min_rr_ratio = min_rr_ratio
    
    def find_targets_for_long(
        self,
        entry_price: float,
        stop_info: Dict,
        levels_analysis: Dict
    ) -> Optional[Dict]:
        """
        Находит TP1 и TP2 для LONG позиции
        
        Args:
            entry_price: Цена входа
            stop_info: Результат DynamicStopLossFinder.find_stop_for_long()
            levels_analysis: Результат OrderbookLevelsAnalyzer.analyze()
            
        Returns:
            {
                'tp1_price': float,
                'tp1_distance_pct': float,
                'tp1_rr': float,
                'tp1_reason': str,
                
                'tp2_price': float,
                'tp2_distance_pct': float,
                'tp2_rr': float,
                'tp2_reason': str,
                
                'is_valid': bool,  # минимум RR >= min_rr_ratio
                'risk_usd': float,
                'reward1_usd': float,
                'reward2_usd': float
            }
        """
        if not stop_info or not stop_info.get('is_valid'):
            return {
                'tp1_price': None,
                'tp2_price': None,
                'is_valid': False,
                'reason': 'Invalid stop loss'
            }
        
        resistance_levels = levels_analysis.get('resistance_levels', [])
        
        if len(resistance_levels) < 1:
            return {
                'tp1_price': None,
                'tp2_price': None,
                'is_valid': False,
                'reason': 'No resistance levels found for take profit'
            }
        
        # Риск = расстояние от входа до стопа
        risk_usd = stop_info['stop_distance_usd']
        
        # TP1 = ПЕРЕД ближайшим resistance (95% distance to avoid rejection at level)
        # This ensures we take profit BEFORE price bounces off resistance
        resistance_target = resistance_levels[0]
        distance_to_resistance = resistance_target - entry_price
        tp1_price = entry_price + (distance_to_resistance * 0.95)  # 95% of distance
        reward1_usd = tp1_price - entry_price
        tp1_distance_pct = (reward1_usd / entry_price) * 100
        
        # REJECT signal if TP1 too close (don't expand - kills accuracy!)
        if tp1_distance_pct > 0 and tp1_distance_pct < self.min_tp_distance_pct:
            return {
                'tp1_price': None,
                'tp2_price': None,
                'is_valid': False,
                'reason': f'TP1 too close: {tp1_distance_pct:.2f}% < {self.min_tp_distance_pct}% minimum (resistance at {tp1_price:.2f})'
            }
        
        tp1_reason = f"95% before resistance at {resistance_target:.2f}"
        tp1_rr = reward1_usd / risk_usd if risk_usd > 0 else 0
        
        # TP2 = ПЕРЕД следующим resistance (если есть)
        tp2_price = None
        tp2_distance_pct = None
        tp2_rr = None
        reward2_usd = None
        tp2_reason = None
        
        if len(resistance_levels) >= 2:
            resistance_target_2 = resistance_levels[1]
            distance_to_resistance_2 = resistance_target_2 - entry_price
            tp2_price = entry_price + (distance_to_resistance_2 * 0.95)  # 95% of distance
            reward2_usd = tp2_price - entry_price
            tp2_distance_pct = (reward2_usd / entry_price) * 100
            tp2_rr = reward2_usd / risk_usd if risk_usd > 0 else 0
            tp2_reason = f"95% before second resistance at {resistance_target_2:.2f}"
        else:
            # Если нет второго уровня, используем TP1 * 1.5
            tp2_price = entry_price + (reward1_usd * 1.5)
            reward2_usd = tp2_price - entry_price
            tp2_distance_pct = (reward2_usd / entry_price) * 100
            tp2_rr = reward2_usd / risk_usd if risk_usd > 0 else 0
            tp2_reason = f"Extended from TP1 (no second resistance)"
        
        # Проверка минимального R/R
        is_valid = tp1_rr >= self.min_rr_ratio
        
        return {
            'tp1_price': round(tp1_price, 8),
            'tp1_distance_pct': round(tp1_distance_pct, 4),
            'tp1_rr': round(tp1_rr, 2),
            'tp1_reason': tp1_reason,
            
            'tp2_price': round(tp2_price, 8),
            'tp2_distance_pct': round(tp2_distance_pct, 4),
            'tp2_rr': round(tp2_rr, 2),
            'tp2_reason': tp2_reason,
            
            'is_valid': is_valid,
            'risk_usd': round(risk_usd, 8),
            'reward1_usd': round(reward1_usd, 8),
            'reward2_usd': round(reward2_usd, 8) if reward2_usd else None
        }
    
    def find_targets_for_short(
        self,
        entry_price: float,
        stop_info: Dict,
        levels_analysis: Dict
    ) -> Optional[Dict]:
        """
        Находит TP1 и TP2 для SHORT позиции
        
        Args:
            entry_price: Цена входа
            stop_info: Результат DynamicStopLossFinder.find_stop_for_short()
            levels_analysis: Результат OrderbookLevelsAnalyzer.analyze()
            
        Returns:
            Аналогично find_targets_for_long
        """
        if not stop_info or not stop_info.get('is_valid'):
            return {
                'tp1_price': None,
                'tp2_price': None,
                'is_valid': False,
                'reason': 'Invalid stop loss'
            }
        
        support_levels = levels_analysis.get('support_levels', [])
        
        if len(support_levels) < 1:
            return {
                'tp1_price': None,
                'tp2_price': None,
                'is_valid': False,
                'reason': 'No support levels found for take profit'
            }
        
        # Риск = расстояние от входа до стопа
        risk_usd = stop_info['stop_distance_usd']
        
        # TP1 = ПЕРЕД ближайшим support (95% distance to avoid rejection at level)
        # This ensures we take profit BEFORE price bounces off support
        support_target = support_levels[0]
        distance_to_support = entry_price - support_target
        tp1_price = entry_price - (distance_to_support * 0.95)  # 95% of distance
        reward1_usd = entry_price - tp1_price
        tp1_distance_pct = (reward1_usd / entry_price) * 100
        
        # REJECT signal if TP1 too close (don't expand - kills accuracy!)
        if tp1_distance_pct > 0 and tp1_distance_pct < self.min_tp_distance_pct:
            return {
                'tp1_price': None,
                'tp2_price': None,
                'is_valid': False,
                'reason': f'TP1 too close: {tp1_distance_pct:.2f}% < {self.min_tp_distance_pct}% minimum (support at {tp1_price:.2f})'
            }
        
        tp1_reason = f"95% before support at {support_target:.2f}"
        tp1_rr = reward1_usd / risk_usd if risk_usd > 0 else 0
        
        # TP2 = ПЕРЕД следующим support (если есть)
        tp2_price = None
        tp2_distance_pct = None
        tp2_rr = None
        reward2_usd = None
        tp2_reason = None
        
        if len(support_levels) >= 2:
            support_target_2 = support_levels[1]
            distance_to_support_2 = entry_price - support_target_2
            tp2_price = entry_price - (distance_to_support_2 * 0.95)  # 95% of distance
            reward2_usd = entry_price - tp2_price
            tp2_distance_pct = (reward2_usd / entry_price) * 100
            tp2_rr = reward2_usd / risk_usd if risk_usd > 0 else 0
            tp2_reason = f"95% before second support at {support_target_2:.2f}"
        else:
            # Если нет второго уровня, используем TP1 * 1.5
            tp2_price = entry_price - (reward1_usd * 1.5)
            reward2_usd = entry_price - tp2_price
            tp2_distance_pct = (reward2_usd / entry_price) * 100
            tp2_rr = reward2_usd / risk_usd if risk_usd > 0 else 0
            tp2_reason = f"Extended from TP1 (no second support)"
        
        # Проверка минимального R/R
        is_valid = tp1_rr >= self.min_rr_ratio
        
        return {
            'tp1_price': round(tp1_price, 8),
            'tp1_distance_pct': round(tp1_distance_pct, 4),
            'tp1_rr': round(tp1_rr, 2),
            'tp1_reason': tp1_reason,
            
            'tp2_price': round(tp2_price, 8),
            'tp2_distance_pct': round(tp2_distance_pct, 4),
            'tp2_rr': round(tp2_rr, 2),
            'tp2_reason': tp2_reason,
            
            'is_valid': is_valid,
            'risk_usd': round(risk_usd, 8),
            'reward1_usd': round(reward1_usd, 8),
            'reward2_usd': round(reward2_usd, 8) if reward2_usd else None
        }
