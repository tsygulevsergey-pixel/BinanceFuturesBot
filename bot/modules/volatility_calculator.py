"""
Volatility Calculator - расчет ATR и классификация волатильности
Используется для динамической адаптации ширины стоп-лосса
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime, timedelta
import asyncpg


class VolatilityCalculator:
    """
    Рассчитывает волатильность актива на основе ATR (Average True Range)
    для определения оптимальной ширины стоп-лосса
    """
    
    def __init__(self, db_pool: asyncpg.Pool, atr_period: int = 14):
        self.db_pool = db_pool
        self.atr_period = atr_period
        self.cache = {}  # {symbol: {'atr': value, 'timestamp': datetime}}
        self.cache_ttl = 60  # секунд
        
    async def calculate_atr(self, symbol: str) -> Optional[Dict]:
        """
        Рассчитывает ATR (Average True Range) за последние N периодов
        
        Returns:
            {
                'atr': float,              # ATR в долларах
                'volatility_pct': float,   # ATR в процентах от цены
                'category': str,           # LOW/MEDIUM/HIGH
                'min_stop_distance': float # минимальная ширина стопа в %
            }
        """
        # Проверка кеша
        if symbol in self.cache:
            cached = self.cache[symbol]
            age = (datetime.now() - cached['timestamp']).total_seconds()
            if age < self.cache_ttl:
                return cached['data']
        
        try:
            # Получить последние N+1 свечей 1m для расчета True Range
            query = """
                SELECT 
                    high_price,
                    low_price,
                    close_price,
                    timestamp
                FROM klines
                WHERE symbol = $1
                    AND interval = '1m'
                    AND timestamp >= NOW() - INTERVAL '20 minutes'
                ORDER BY timestamp DESC
                LIMIT $2
            """
            
            rows = await self.db_pool.fetch(query, symbol, self.atr_period + 1)
            
            if len(rows) < self.atr_period + 1:
                return None
            
            # Рассчитать True Range для каждой свечи
            true_ranges = []
            current_price = float(rows[0]['close_price'])
            
            for i in range(len(rows) - 1):
                current = rows[i]
                previous = rows[i + 1]
                
                high = float(current['high_price'])
                low = float(current['low_price'])
                prev_close = float(previous['close_price'])
                
                # True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            # ATR = среднее True Range за period свечей
            atr = sum(true_ranges[:self.atr_period]) / self.atr_period
            
            # Нормализовать в проценты от текущей цены
            volatility_pct = (atr / current_price) * 100
            
            # Классифицировать волатильность
            if volatility_pct < 0.3:
                category = 'LOW'
                min_stop_distance = 0.3
            elif volatility_pct < 0.7:
                category = 'MEDIUM'
                min_stop_distance = 0.5
            else:
                category = 'HIGH'
                min_stop_distance = 0.8
            
            result = {
                'atr': round(atr, 8),
                'volatility_pct': round(volatility_pct, 4),
                'category': category,
                'min_stop_distance': min_stop_distance,
                'current_price': current_price
            }
            
            # Кешировать результат
            self.cache[symbol] = {
                'data': result,
                'timestamp': datetime.now()
            }
            
            return result
            
        except Exception as e:
            print(f"❌ [VolatilityCalculator] Error calculating ATR for {symbol}: {e}")
            return None
    
    async def get_working_range(self, symbol: str, multiplier: float = 3.0) -> Optional[Dict]:
        """
        Рассчитывает рабочий диапазон для анализа уровней
        Диапазон = текущая цена ± (multiplier * ATR)
        
        Args:
            symbol: Символ актива
            multiplier: Множитель ATR (по умолчанию 3.0)
            
        Returns:
            {
                'lower_bound': float,  # нижняя граница
                'upper_bound': float,  # верхняя граница
                'current_price': float,
                'range_pct': float     # диапазон в %
            }
        """
        volatility = await self.calculate_atr(symbol)
        if not volatility:
            return None
        
        atr = volatility['atr']
        current_price = volatility['current_price']
        
        # Рабочий диапазон = current_price ± (multiplier * ATR)
        lower_bound = current_price - (multiplier * atr)
        upper_bound = current_price + (multiplier * atr)
        
        range_pct = ((upper_bound - lower_bound) / current_price) * 100
        
        return {
            'lower_bound': round(lower_bound, 8),
            'upper_bound': round(upper_bound, 8),
            'current_price': current_price,
            'range_pct': round(range_pct, 2),
            'atr': atr,
            'multiplier': multiplier
        }
    
    def clear_cache(self):
        """Очистить кеш волатильности"""
        self.cache.clear()
