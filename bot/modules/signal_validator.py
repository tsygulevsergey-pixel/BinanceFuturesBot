"""
Signal Validator - фильтрация сигналов по всем критериям
Отклоняет сигналы с плохим R/R, слабым имбалансом, широким стопом и т.д.
"""

from typing import Dict, Optional


class SignalValidator:
    """
    Валидирует торговые сигналы по множественным критериям
    Отсеивает сигналы низкого качества
    """
    
    def __init__(self, config: Dict):
        """
        Args:
            config: Конфиг с параметрами фильтрации
        """
        # GLOBAL imbalance thresholds (200 levels, more smoothed than local 10 levels)
        self.min_imbalance = config.get('ORDERBOOK_IMBALANCE_THRESHOLD', 0.15)  # was 0.25 for local
        self.min_large_trades = config.get('MIN_LARGE_TRADES', 2)
        self.min_volume_intensity = config.get('VOLUME_INTENSITY_THRESHOLD', 1.5)
        self.min_rr_ratio = config.get('MIN_RR_RATIO', 0.8)
        self.max_stop_distance = config.get('MAX_STOP_DISTANCE_PCT', 1.5)
        
        # Priority thresholds for GLOBAL imbalance (200 levels)
        self.priority_high = config.get('PRIORITY_HIGH_THRESHOLD', 0.25)    # was 0.35 for local
        self.priority_medium = config.get('PRIORITY_MEDIUM_THRESHOLD', 0.20) # was 0.30 for local
    
    def validate(
        self,
        imbalance: float,
        large_trades_count: int,
        volume_intensity: float,
        stop_info: Dict,
        tp_info: Dict,
        levels_analysis: Dict
    ) -> Dict:
        """
        Полная валидация сигнала
        
        Args:
            imbalance: Текущий дисбаланс стакана (абсолютное значение)
            large_trades_count: Количество крупных сделок за последние 5 мин
            volume_intensity: Интенсивность объема (кратно среднему)
            stop_info: Результат DynamicStopLossFinder
            tp_info: Результат DynamicTakeProfitFinder
            levels_analysis: Результат OrderbookLevelsAnalyzer
            
        Returns:
            {
                'is_valid': bool,
                'priority': str,  # HIGH/MEDIUM/LOW
                'rejection_reasons': [str],  # причины отклонения
                'quality_score': float,  # 0-100
                'warnings': [str]  # предупреждения (не критично)
            }
        """
        rejection_reasons = []
        warnings = []
        
        # === КРИТИЧЕСКИЕ ФИЛЬТРЫ (отклонение сигнала) ===
        
        # 1. Проверка имбаланса
        if abs(imbalance) < self.min_imbalance:
            rejection_reasons.append(
                f"Weak imbalance: {abs(imbalance):.3f} < {self.min_imbalance}"
            )
        
        # 2. Проверка крупных сделок
        if large_trades_count < self.min_large_trades:
            rejection_reasons.append(
                f"Few large trades: {large_trades_count} < {self.min_large_trades}"
            )
        
        # 3. Проверка объема
        if volume_intensity < self.min_volume_intensity:
            rejection_reasons.append(
                f"Low volume: {volume_intensity:.2f}x < {self.min_volume_intensity}x"
            )
        
        # 4. Проверка стопа
        if not stop_info or not stop_info.get('is_valid'):
            rejection_reasons.append(
                f"Invalid stop: {stop_info.get('reason', 'unknown') if stop_info else 'no stop info'}"
            )
        elif stop_info.get('stop_distance_pct', 999) > self.max_stop_distance:
            rejection_reasons.append(
                f"Stop too wide: {stop_info['stop_distance_pct']:.2f}% > {self.max_stop_distance}%"
            )
        
        # 5. Проверка R/R ratio
        if not tp_info or not tp_info.get('is_valid'):
            rejection_reasons.append(
                f"Invalid targets: {tp_info.get('reason', 'unknown') if tp_info else 'no tp info'}"
            )
        elif tp_info.get('tp1_rr', 0) < self.min_rr_ratio:
            rejection_reasons.append(
                f"Bad R/R: {tp_info.get('tp1_rr', 0):.2f} < {self.min_rr_ratio}"
            )
        
        # 6. Проверка наличия уровней
        total_levels = levels_analysis.get('total_levels_found', 0)
        if total_levels == 0:
            rejection_reasons.append("No clear levels found in orderbook")
        
        # === ПРЕДУПРЕЖДЕНИЯ (не критично, но отмечаем) ===
        
        # Предупреждение если объем слабоват
        if self.min_volume_intensity <= volume_intensity < 2.0:
            warnings.append(f"Volume could be stronger ({volume_intensity:.2f}x)")
        
        # Предупреждение если R/R не идеальный
        if tp_info and self.min_rr_ratio <= tp_info.get('tp1_rr', 0) < 1.5:
            warnings.append(f"R/R acceptable but not ideal ({tp_info['tp1_rr']:.2f})")
        
        # === ПРИОРИТИЗАЦИЯ ===
        
        priority = self._calculate_priority(abs(imbalance))
        
        # === ОЦЕНКА КАЧЕСТВА (0-100) ===
        
        quality_score = self._calculate_quality_score(
            imbalance=abs(imbalance),
            large_trades_count=large_trades_count,
            volume_intensity=volume_intensity,
            rr_ratio=tp_info.get('tp1_rr', 0) if tp_info else 0,
            total_levels=total_levels
        )
        
        # === ФИНАЛЬНОЕ РЕШЕНИЕ ===
        
        is_valid = len(rejection_reasons) == 0
        
        return {
            'is_valid': is_valid,
            'priority': priority,
            'rejection_reasons': rejection_reasons,
            'quality_score': round(quality_score, 1),
            'warnings': warnings,
            'imbalance': abs(imbalance),
            'large_trades': large_trades_count,
            'volume_intensity': volume_intensity,
            'rr_ratio': tp_info.get('tp1_rr') if tp_info else None
        }
    
    def _calculate_priority(self, imbalance: float) -> str:
        """Определить приоритет сигнала на основе имбаланса"""
        if imbalance >= self.priority_high:
            return 'HIGH'
        elif imbalance >= self.priority_medium:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _calculate_quality_score(
        self,
        imbalance: float,
        large_trades_count: int,
        volume_intensity: float,
        rr_ratio: float,
        total_levels: int
    ) -> float:
        """
        Рассчитать качество сигнала (0-100)
        
        Компоненты:
        - Imbalance: 0-30 баллов
        - Large trades: 0-20 баллов
        - Volume: 0-20 баллов
        - R/R ratio: 0-20 баллов
        - Levels clarity: 0-10 баллов
        """
        score = 0.0
        
        # 1. Imbalance (0-30) - GLOBAL thresholds (200 levels)
        if imbalance >= 0.25:  # HIGH: ≥25% (was 0.35 for local)
            score += 30
        elif imbalance >= 0.20:  # MEDIUM: ≥20% (was 0.30 for local)
            score += 25
        elif imbalance >= 0.15:  # LOW: ≥15% (was 0.25 for local)
            score += 15
        else:
            score += max(0, imbalance * 60)  # пропорционально (adjusted multiplier)
        
        # 2. Large trades (0-20)
        if large_trades_count >= 5:
            score += 20
        elif large_trades_count >= 3:
            score += 15
        elif large_trades_count >= 2:
            score += 10
        else:
            score += large_trades_count * 5
        
        # 3. Volume intensity (0-20)
        if volume_intensity >= 3.0:
            score += 20
        elif volume_intensity >= 2.0:
            score += 15
        elif volume_intensity >= 1.5:
            score += 10
        else:
            score += max(0, (volume_intensity - 1.0) * 20)
        
        # 4. R/R ratio (0-20)
        if rr_ratio >= 2.0:
            score += 20
        elif rr_ratio >= 1.5:
            score += 15
        elif rr_ratio >= 1.0:
            score += 10
        elif rr_ratio >= 0.8:
            score += 5
        else:
            score += 0
        
        # 5. Levels clarity (0-10)
        if total_levels >= 5:
            score += 10
        elif total_levels >= 3:
            score += 7
        elif total_levels >= 1:
            score += 5
        else:
            score += 0
        
        return min(100, score)
