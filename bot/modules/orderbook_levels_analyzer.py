"""
Orderbook Levels Analyzer - анализ стакана и объемных зон
Находит кластеры ордеров и определяет уровни поддержки/сопротивления
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import asyncpg


class OrderbookLevelsAnalyzer:
    """
    Анализирует стакан ордеров и объемный профиль для определения
    ключевых уровней поддержки и сопротивления
    """
    
    def __init__(
        self, 
        db_pool: asyncpg.Pool,
        cluster_threshold: float = 2.0,  # объем > среднего в 2x = кластер
        min_volume_pct: float = 10.0,    # минимум 10% от макс объема
        relevant_hours: int = 6          # последние 6 часов
    ):
        self.db_pool = db_pool
        self.cluster_threshold = cluster_threshold
        self.min_volume_pct = min_volume_pct
        self.relevant_hours = relevant_hours
        
    async def analyze(
        self, 
        symbol: str, 
        current_price: float,
        working_range: Dict,
        orderbook_snapshot: Dict
    ) -> Optional[Dict]:
        """
        Полный анализ стакана и объемных зон
        
        Args:
            symbol: Символ актива
            current_price: Текущая цена
            working_range: Рабочий диапазон от VolatilityCalculator
            orderbook_snapshot: Снимок стакана {bids: [...], asks: [...]}
            
        Returns:
            {
                'support_levels': [price1, price2, ...],  # отсортировано по убыванию
                'resistance_levels': [price1, price2, ...],  # отсортировано по возрастанию
                'strongest_support': float,
                'strongest_resistance': float,
                'poc': float,  # Point of Control
                'low_volume_zones': [(lower, upper), ...],
                'volume_profile': {price: volume, ...}
            }
        """
        lower_bound = working_range['lower_bound']
        upper_bound = working_range['upper_bound']
        
        print(f"📊 [OrderbookLevelsAnalyzer] Analyzing {symbol}")
        print(f"   Working range: {lower_bound:.2f} - {upper_bound:.2f}")
        
        # 1. Анализ текущего стакана (кластеры ордеров)
        orderbook_clusters = self._find_orderbook_clusters(
            orderbook_snapshot,
            lower_bound,
            upper_bound,
            current_price
        )
        
        # 2. Построение объемного профиля (последние 6 часов)
        volume_profile = await self._build_volume_profile(
            symbol,
            lower_bound,
            upper_bound
        )
        
        # 3. Объединить данные стакана и объемного профиля
        combined_levels = self._combine_levels(
            orderbook_clusters,
            volume_profile,
            current_price
        )
        
        # 4. Классифицировать уровни на support/resistance
        support_levels = sorted(
            [lvl for lvl in combined_levels['all_levels'] if lvl < current_price],
            reverse=True  # от ближайшего к дальнему
        )
        
        resistance_levels = sorted(
            [lvl for lvl in combined_levels['all_levels'] if lvl > current_price]
        )
        
        # 5. Определить strongest уровни
        strongest_support = support_levels[0] if support_levels else None
        strongest_resistance = resistance_levels[0] if resistance_levels else None
        
        # 6. Найти POC (Point of Control) - уровень с максимальным объемом
        poc = combined_levels['poc']
        
        # 7. Найти зоны низкого объема
        low_volume_zones = self._find_low_volume_zones(
            volume_profile,
            lower_bound,
            upper_bound
        )
        
        result = {
            'support_levels': support_levels[:5],  # топ 5
            'resistance_levels': resistance_levels[:5],
            'strongest_support': strongest_support,
            'strongest_resistance': strongest_resistance,
            'poc': poc,
            'low_volume_zones': low_volume_zones,
            'volume_profile': volume_profile,
            'total_levels_found': len(combined_levels['all_levels'])
        }
        
        print(f"✅ [OrderbookLevelsAnalyzer] Found {len(support_levels)} support, {len(resistance_levels)} resistance")
        
        return result
    
    def _find_orderbook_clusters(
        self,
        orderbook: Dict,
        lower_bound: float,
        upper_bound: float,
        current_price: float
    ) -> Dict:
        """
        Находит кластеры ордеров в стакане (зоны концентрации объема)
        """
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        # Bin size = 0.2% from price (optimized for 500-level deep analysis)
        # 0.1% too narrow (over-fragmentation), 1.0% too wide (lost precision)
        # 0.2% is sweet spot: BTC $90K → $180 bins (good granularity)
        bin_size = current_price * 0.002  # 0.2%
        
        bid_clusters = defaultdict(float)
        ask_clusters = defaultdict(float)
        
        # Группировать bids
        for price, qty in bids:
            price = float(price)  # Convert string to float
            qty = float(qty)
            if lower_bound <= price <= upper_bound:
                bin_price = round(price / bin_size) * bin_size
                bid_clusters[bin_price] += qty
        
        # Группировать asks
        for price, qty in asks:
            price = float(price)  # Convert string to float
            qty = float(qty)
            if lower_bound <= price <= upper_bound:
                bin_price = round(price / bin_size) * bin_size
                ask_clusters[bin_price] += qty
        
        # Найти средний объем
        all_volumes = list(bid_clusters.values()) + list(ask_clusters.values())
        avg_volume = sum(all_volumes) / len(all_volumes) if all_volumes else 0
        
        # Фильтровать кластеры (объем > среднего * threshold)
        threshold = avg_volume * self.cluster_threshold
        
        significant_bids = {
            price: vol for price, vol in bid_clusters.items()
            if vol > threshold
        }
        
        significant_asks = {
            price: vol for price, vol in ask_clusters.items()
            if vol > threshold
        }
        
        return {
            'bid_clusters': significant_bids,
            'ask_clusters': significant_asks,
            'avg_volume': avg_volume,
            'threshold': threshold
        }
    
    async def _build_volume_profile(
        self,
        symbol: str,
        lower_bound: float,
        upper_bound: float
    ) -> Dict[float, float]:
        """
        Строит объемный профиль на основе исторических свечей
        Использует только последние 6 часов (актуальные данные)
        """
        try:
            # Получить свечи за последние 6 часов
            query = """
                SELECT 
                    high,
                    low,
                    close,
                    volume,
                    timestamp
                FROM klines
                WHERE symbol = $1
                    AND interval = '1m'
                    AND timestamp >= NOW() - INTERVAL '6 hours'
                ORDER BY timestamp DESC
            """
            
            rows = await self.db_pool.fetch(query, symbol)
            
            if not rows:
                return {}
            
            # Группировать объем по ценовым уровням
            volume_profile = defaultdict(float)
            
            # Bin size = 0.2% from average price (optimized for volume profile)
            # Matches orderbook cluster bin size for consistency
            avg_price = (lower_bound + upper_bound) / 2
            bin_size = avg_price * 0.002  # 0.2%
            
            for row in rows:
                low = float(row['low'])
                high = float(row['high'])
                volume = float(row['volume'])
                
                # Распределить объем свечи по ценовым уровням
                if high != low:
                    levels = int((high - low) / bin_size) + 1
                    volume_per_level = volume / levels
                    
                    for i in range(levels):
                        price = low + (i * bin_size)
                        if lower_bound <= price <= upper_bound:
                            bin_price = round(price / bin_size) * bin_size
                            volume_profile[bin_price] += volume_per_level
            
            return dict(volume_profile)
            
        except Exception as e:
            print(f"❌ [OrderbookLevelsAnalyzer] Error building volume profile: {e}")
            return {}
    
    def _combine_levels(
        self,
        orderbook_clusters: Dict,
        volume_profile: Dict[float, float],
        current_price: float
    ) -> Dict:
        """
        Объединяет данные стакана и объемного профиля
        Фильтрует уровни по минимальному проценту объема
        """
        # Найти максимальный объем для нормализации
        all_volumes = list(volume_profile.values())
        if orderbook_clusters['bid_clusters']:
            all_volumes.extend(orderbook_clusters['bid_clusters'].values())
        if orderbook_clusters['ask_clusters']:
            all_volumes.extend(orderbook_clusters['ask_clusters'].values())
        
        max_volume = max(all_volumes) if all_volumes else 1
        min_volume_threshold = max_volume * (self.min_volume_pct / 100)
        
        # Собрать все значимые уровни
        significant_levels = set()
        level_volumes = {}
        
        # Добавить уровни из объемного профиля
        for price, volume in volume_profile.items():
            if volume >= min_volume_threshold:
                significant_levels.add(price)
                level_volumes[price] = volume
        
        # Добавить кластеры из стакана (bids)
        for price, volume in orderbook_clusters['bid_clusters'].items():
            # Нормализовать объем стакана к объему профиля
            normalized_vol = volume * (max_volume / 10)  # коэффициент адаптации
            if normalized_vol >= min_volume_threshold:
                significant_levels.add(price)
                level_volumes[price] = normalized_vol
        
        # Добавить кластеры из стакана (asks)
        for price, volume in orderbook_clusters['ask_clusters'].items():
            normalized_vol = volume * (max_volume / 10)
            if normalized_vol >= min_volume_threshold:
                significant_levels.add(price)
                level_volumes[price] = normalized_vol
        
        # Найти POC (уровень с максимальным объемом)
        poc = max(level_volumes.items(), key=lambda x: x[1])[0] if level_volumes else current_price
        
        return {
            'all_levels': list(significant_levels),
            'level_volumes': level_volumes,
            'poc': poc,
            'max_volume': max_volume,
            'min_threshold': min_volume_threshold
        }
    
    def _find_low_volume_zones(
        self,
        volume_profile: Dict[float, float],
        lower_bound: float,
        upper_bound: float
    ) -> List[Tuple[float, float]]:
        """
        Находит зоны низкого объема (где цена пройдет легко)
        """
        if not volume_profile:
            return []
        
        avg_volume = sum(volume_profile.values()) / len(volume_profile)
        low_volume_threshold = avg_volume * 0.5  # объем < 50% среднего
        
        # Найти зоны низкого объема
        low_zones = []
        zone_start = None
        
        sorted_prices = sorted(volume_profile.keys())
        
        for i, price in enumerate(sorted_prices):
            volume = volume_profile[price]
            
            if volume < low_volume_threshold:
                if zone_start is None:
                    zone_start = price
            else:
                if zone_start is not None:
                    # Завершить зону
                    low_zones.append((zone_start, sorted_prices[i-1]))
                    zone_start = None
        
        # Закрыть последнюю зону если осталась открытой
        if zone_start is not None:
            low_zones.append((zone_start, sorted_prices[-1]))
        
        return low_zones[:3]  # топ 3 зоны
