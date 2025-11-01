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
        
        # TP1 = ближайший resistance
        tp1_price = resistance_levels[0]
        reward1_usd = tp1_price - entry_price
        tp1_distance_pct = (reward1_usd / entry_price) * 100
        
        # ENFORCE MINIMUM TP DISTANCE: Если TP слишком близко, расширить до минимума
        tp1_reason = f"First resistance at {tp1_price:.2f}"
        if tp1_distance_pct > 0 and tp1_distance_pct < self.min_tp_distance_pct:
            # Расширить TP до минимального расстояния
            min_reward_usd = entry_price * (self.min_tp_distance_pct / 100)
            tp1_price = entry_price + min_reward_usd
            reward1_usd = min_reward_usd
            tp1_distance_pct = self.min_tp_distance_pct
            tp1_reason = f"Expanded to minimum {self.min_tp_distance_pct}% (resistance at {resistance_levels[0]:.2f} too close)"
        
        tp1_rr = reward1_usd / risk_usd if risk_usd > 0 else 0
        
        # TP2 = следующий resistance (если есть)
        tp2_price = None
        tp2_distance_pct = None
        tp2_rr = None
        reward2_usd = None
        tp2_reason = None
        
        if len(resistance_levels) >= 2:
            tp2_price = resistance_levels[1]
            reward2_usd = tp2_price - entry_price
            tp2_distance_pct = (reward2_usd / entry_price) * 100
            tp2_rr = reward2_usd / risk_usd if risk_usd > 0 else 0
            tp2_reason = f"Second resistance at {tp2_price:.2f}"
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
        
        # TP1 = ближайший support (support_levels уже отсортированы от ближайшего)
        tp1_price = support_levels[0]
        reward1_usd = entry_price - tp1_price
        tp1_distance_pct = (reward1_usd / entry_price) * 100
        
        # ENFORCE MINIMUM TP DISTANCE: Если TP слишком близко, расширить до минимума
        tp1_reason = f"First support at {tp1_price:.2f}"
        if tp1_distance_pct > 0 and tp1_distance_pct < self.min_tp_distance_pct:
            # Расширить TP до минимального расстояния
            min_reward_usd = entry_price * (self.min_tp_distance_pct / 100)
            tp1_price = entry_price - min_reward_usd
            reward1_usd = min_reward_usd
            tp1_distance_pct = self.min_tp_distance_pct
            tp1_reason = f"Expanded to minimum {self.min_tp_distance_pct}% (support at {support_levels[0]:.2f} too close)"
        
        tp1_rr = reward1_usd / risk_usd if risk_usd > 0 else 0
        
        # TP2 = следующий support
        tp2_price = None
        tp2_distance_pct = None
        tp2_rr = None
        reward2_usd = None
        tp2_reason = None
        
        if len(support_levels) >= 2:
            tp2_price = support_levels[1]
            reward2_usd = entry_price - tp2_price
            tp2_distance_pct = (reward2_usd / entry_price) * 100
            tp2_rr = reward2_usd / risk_usd if risk_usd > 0 else 0
            tp2_reason = f"Second support at {tp2_price:.2f}"
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
