"""
Dynamic Stop Loss Finder - размещение стопа за САМОЙ МОЩНОЙ рыночной зоной

КРИТИЧЕСКАЯ ЛОГИКА:
- Бот находит ВСЕ зоны плотности в направлении SL
- Выбирает зону с МАКСИМАЛЬНЫМ объёмом (не ближайшую!)
- Ставит SL за этой зоной на расстоянии 1.5 ATR

ПОЧЕМУ ЭТО РАБОТАЕТ:
- Цена может несколько раз протестировать слабые уровни
- Но остановится у самой мощной зоны (там большой объём)
- SL за мощной зоной = защита от ранних стопов при правильном направлении
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
        
        # Размещение: За strongest_support минус 1.5 ATR (было 0.5)
        # КРИТИЧНО: strongest_support теперь = уровень с МАКСИМАЛЬНЫМ объёмом (не ближайший!)
        # Логика: SL за САМОЙ МОЩНОЙ зоной защищает от ранних стопов
        # Цена может несколько раз тестировать слабые зоны, но остановится у мощной
        # ATR 1.5x дает достаточный буфер для микро-волатильности
        stop_loss_price = strongest_support - (atr * 1.5)
        
        # Рассчитать расстояние от входа
        stop_distance_usd = entry_price - stop_loss_price
        stop_distance_pct = (stop_distance_usd / entry_price) * 100
        
        # NO minimum distance check for SL - the closer the stop to support, the better!
        # Only check maximum distance to avoid overly wide stops
        reason = f"Below support cluster at {strongest_support:.2f}"
        
        is_valid = (stop_distance_pct > 0 and stop_distance_pct <= self.max_stop_distance_pct)
        
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
        
        # Размещение: За strongest_resistance плюс 1.5 ATR (было 0.5)
        # КРИТИЧНО: strongest_resistance теперь = уровень с МАКСИМАЛЬНЫМ объёмом (не ближайший!)
        # Логика: SL за САМОЙ МОЩНОЙ зоной защищает от ранних стопов
        # Цена может несколько раз тестировать слабые зоны, но остановится у мощной
        # ATR 1.5x дает достаточный буфер для микро-волатильности
        stop_loss_price = strongest_resistance + (atr * 1.5)
        
        # Рассчитать расстояние от входа
        stop_distance_usd = stop_loss_price - entry_price
        stop_distance_pct = (stop_distance_usd / entry_price) * 100
        
        # NO minimum distance check for SL - the closer the stop to resistance, the better!
        # Only check maximum distance to avoid overly wide stops
        reason = f"Above resistance cluster at {strongest_resistance:.2f}"
        
        is_valid = (stop_distance_pct > 0 and stop_distance_pct <= self.max_stop_distance_pct)
        
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
