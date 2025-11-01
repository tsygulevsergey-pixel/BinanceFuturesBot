"""
Dynamic Stop Loss Finder - размещение стопа за рыночными уровнями
Стоп ставится ЗА зоной поддержки (для LONG) или сопротивления (для SHORT)
"""

from typing import Dict, Optional


class DynamicStopLossFinder:
    """
    Находит оптимальное размещение стоп-лосса на основе
    реальных уровней поддержки/сопротивления из стакана
    """
    
    def __init__(self, min_stop_distance_pct: float = 0.15, max_stop_distance_pct: float = 1.5):
        """
        Args:
            min_stop_distance_pct: Минимальное расстояние стопа от входа в % (защита от микро-движений)
            max_stop_distance_pct: Максимальное расстояние стопа от входа в %
        """
        self.min_stop_distance_pct = min_stop_distance_pct
        self.max_stop_distance_pct = max_stop_distance_pct
    
    def find_stop_for_long(
        self,
        entry_price: float,
        levels_analysis: Dict,
        volatility: Dict
    ) -> Optional[Dict]:
        """
        Находит стоп для LONG позиции
        
        Args:
            entry_price: Цена входа
            levels_analysis: Результат OrderbookLevelsAnalyzer.analyze()
            volatility: Результат VolatilityCalculator.calculate_atr()
            
        Returns:
            {
                'stop_loss_price': float,
                'stop_distance_pct': float,
                'stop_distance_usd': float,
                'reason': str,  # объяснение размещения
                'is_valid': bool,
                'support_level': float  # уровень за которым стоп
            }
        """
        support_levels = levels_analysis.get('support_levels', [])
        strongest_support = levels_analysis.get('strongest_support')
        atr = volatility['atr']
        
        if not strongest_support:
            return {
                'stop_loss_price': None,
                'stop_distance_pct': None,
                'stop_distance_usd': None,
                'reason': 'No support levels found in working range',
                'is_valid': False,
                'support_level': None
            }
        
        # Размещение: За strongest_support минус половина ATR
        # Это гарантирует, что стоп за зоной поддержки, а не внутри неё
        stop_loss_price = strongest_support - (atr * 0.5)
        
        # Рассчитать расстояние от входа
        stop_distance_usd = entry_price - stop_loss_price
        stop_distance_pct = (stop_distance_usd / entry_price) * 100
        
        # REJECT signal if stop too close (don't expand - kills accuracy!)
        if stop_distance_pct > 0 and stop_distance_pct < self.min_stop_distance_pct:
            return {
                'stop_loss_price': None,
                'stop_distance_pct': None,
                'stop_distance_usd': None,
                'reason': f'Stop too close: {stop_distance_pct:.2f}% < {self.min_stop_distance_pct}% minimum (support at {strongest_support:.2f})',
                'is_valid': False,
                'support_level': strongest_support
            }
        
        reason = f"Below support cluster at {strongest_support:.2f}"
        
        # Проверить ограничения максимального расстояния
        is_valid = (stop_distance_pct <= self.max_stop_distance_pct)
        
        if not is_valid:
            if stop_distance_pct > self.max_stop_distance_pct:
                reason += f" (TOO WIDE: {stop_distance_pct:.2f}% > {self.max_stop_distance_pct}%)"
            elif stop_distance_pct <= 0:
                reason += " (INVALID: stop above entry)"
        
        return {
            'stop_loss_price': round(stop_loss_price, 8),
            'stop_distance_pct': round(stop_distance_pct, 4),
            'stop_distance_usd': round(stop_distance_usd, 8),
            'reason': reason,
            'is_valid': is_valid,
            'support_level': strongest_support
        }
    
    def find_stop_for_short(
        self,
        entry_price: float,
        levels_analysis: Dict,
        volatility: Dict
    ) -> Optional[Dict]:
        """
        Находит стоп для SHORT позиции
        
        Args:
            entry_price: Цена входа
            levels_analysis: Результат OrderbookLevelsAnalyzer.analyze()
            volatility: Результат VolatilityCalculator.calculate_atr()
            
        Returns:
            {
                'stop_loss_price': float,
                'stop_distance_pct': float,
                'stop_distance_usd': float,
                'reason': str,
                'is_valid': bool,
                'resistance_level': float  # уровень за которым стоп
            }
        """
        resistance_levels = levels_analysis.get('resistance_levels', [])
        strongest_resistance = levels_analysis.get('strongest_resistance')
        atr = volatility['atr']
        
        if not strongest_resistance:
            return {
                'stop_loss_price': None,
                'stop_distance_pct': None,
                'stop_distance_usd': None,
                'reason': 'No resistance levels found in working range',
                'is_valid': False,
                'resistance_level': None
            }
        
        # Размещение: За strongest_resistance плюс половина ATR
        stop_loss_price = strongest_resistance + (atr * 0.5)
        
        # Рассчитать расстояние от входа
        stop_distance_usd = stop_loss_price - entry_price
        stop_distance_pct = (stop_distance_usd / entry_price) * 100
        
        # REJECT signal if stop too close (don't expand - kills accuracy!)
        if stop_distance_pct > 0 and stop_distance_pct < self.min_stop_distance_pct:
            return {
                'stop_loss_price': None,
                'stop_distance_pct': None,
                'stop_distance_usd': None,
                'reason': f'Stop too close: {stop_distance_pct:.2f}% < {self.min_stop_distance_pct}% minimum (resistance at {strongest_resistance:.2f})',
                'is_valid': False,
                'resistance_level': strongest_resistance
            }
        
        reason = f"Above resistance cluster at {strongest_resistance:.2f}"
        
        # Проверить ограничения максимального расстояния
        is_valid = (stop_distance_pct <= self.max_stop_distance_pct)
        
        if not is_valid:
            if stop_distance_pct > self.max_stop_distance_pct:
                reason += f" (TOO WIDE: {stop_distance_pct:.2f}% > {self.max_stop_distance_pct}%)"
            elif stop_distance_pct <= 0:
                reason += " (INVALID: stop below entry)"
        
        return {
            'stop_loss_price': round(stop_loss_price, 8),
            'stop_distance_pct': round(stop_distance_pct, 4),
            'stop_distance_usd': round(stop_distance_usd, 8),
            'reason': reason,
            'is_valid': is_valid,
            'resistance_level': strongest_resistance
        }
