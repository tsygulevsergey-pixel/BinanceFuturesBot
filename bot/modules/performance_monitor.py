"""
Performance Monitor - tracks and calculates performance metrics
Metrics: win rate, PnL, Sharpe ratio, max drawdown, TP/SL hit rates
Updates daily and provides statistics for /stats command
"""
from typing import Dict, List
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.database import db_manager, Trade, Signal, PerformanceMetrics, DailyStats
import numpy as np
from decimal import Decimal

class PerformanceMonitor:
    def __init__(self):
        logger.info("🔧 [PerformanceMonitor] Initialized")
    
    def calculate_daily_metrics(self) -> Dict:
        try:
            today = datetime.now().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            with db_manager.get_session() as session:
                closed_trades = session.query(Trade).filter(
                    Trade.exit_time >= today_start,
                    Trade.status == 'CLOSED'
                ).all()
                
                if not closed_trades:
                    logger.info("📊 [PerformanceMonitor] No closed trades today")
                    return {}
                
                win_count = sum(1 for t in closed_trades if float(t.pnl_percent or 0) > 0)
                loss_count = len(closed_trades) - win_count
                win_rate = (win_count / len(closed_trades)) * 100 if closed_trades else 0
                
                pnl_list = [float(t.pnl_percent or 0) for t in closed_trades]
                total_pnl = sum(pnl_list)
                avg_pnl = total_pnl / len(pnl_list) if pnl_list else 0
                max_profit = max(pnl_list) if pnl_list else 0
                max_loss = min(pnl_list) if pnl_list else 0
                
                hold_times = [t.hold_time_minutes for t in closed_trades if t.hold_time_minutes]
                avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0
                
                sharpe_ratio = self._calculate_sharpe_ratio(pnl_list)
                max_drawdown = self._calculate_max_drawdown(pnl_list)
                
                tp1_count = sum(1 for t in closed_trades if t.exit_reason == 'TAKE_PROFIT_1')
                tp2_count = sum(1 for t in closed_trades if t.exit_reason == 'TAKE_PROFIT_2')
                sl_count = sum(1 for t in closed_trades if t.exit_reason == 'STOP_LOSS')
                
                total_signals = session.query(Signal).filter(
                    Signal.created_at >= today_start
                ).count()
                
                metrics = {
                    'date': today,
                    'signals_generated': total_signals,
                    'signals_triggered': len(closed_trades),
                    'win_count': win_count,
                    'loss_count': loss_count,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'average_pnl': avg_pnl,
                    'max_profit': max_profit,
                    'max_loss': max_loss,
                    'average_hold_time': avg_hold_time,
                    'sharpe_ratio': sharpe_ratio,
                    'max_drawdown': max_drawdown,
                    'tp1_hit_count': tp1_count,
                    'tp2_hit_count': tp2_count,
                    'sl_hit_count': sl_count
                }
                
                logger.info(
                    f"📊 [PerformanceMonitor] Daily metrics: "
                    f"Signals={total_signals}, Trades={len(closed_trades)}, "
                    f"WinRate={win_rate:.1f}%, PnL={total_pnl:+.2f}%"
                )
                
                return metrics
                
        except Exception as e:
            logger.error(f"❌ [PerformanceMonitor] Error calculating daily metrics: {e}")
            return {}
    
    def _calculate_sharpe_ratio(self, pnl_list: List[float]) -> float:
        try:
            if not pnl_list or len(pnl_list) < 2:
                return 0.0
            
            returns = np.array(pnl_list) / 100
            
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            
            if std_return == 0:
                return 0.0
            
            sharpe_ratio = (mean_return / std_return) * np.sqrt(365)
            
            return float(sharpe_ratio)
            
        except Exception as e:
            logger.error(f"❌ [PerformanceMonitor] Error calculating Sharpe ratio: {e}")
            return 0.0
    
    def _calculate_max_drawdown(self, pnl_list: List[float]) -> float:
        try:
            if not pnl_list:
                return 0.0
            
            cumulative = np.cumsum(pnl_list)
            
            running_max = np.maximum.accumulate(cumulative)
            drawdown = running_max - cumulative
            max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0.0
            
            return float(max_drawdown)
            
        except Exception as e:
            logger.error(f"❌ [PerformanceMonitor] Error calculating max drawdown: {e}")
            return 0.0
    
    def save_metrics(self, metrics: Dict):
        try:
            if not metrics:
                return
            
            with db_manager.get_session() as session:
                perf_metric = PerformanceMetrics(
                    date=metrics['date'],
                    signals_generated=metrics['signals_generated'],
                    signals_triggered=metrics['signals_triggered'],
                    win_count=metrics['win_count'],
                    loss_count=metrics['loss_count'],
                    win_rate=metrics['win_rate'],
                    total_pnl=Decimal(str(metrics['total_pnl'])),
                    average_pnl=Decimal(str(metrics['average_pnl'])),
                    max_profit=Decimal(str(metrics['max_profit'])),
                    max_loss=Decimal(str(metrics['max_loss'])),
                    average_hold_time=metrics['average_hold_time'],
                    sharpe_ratio=metrics['sharpe_ratio'],
                    max_drawdown=metrics['max_drawdown'],
                    tp1_hit_count=metrics['tp1_hit_count'],
                    tp2_hit_count=metrics['tp2_hit_count'],
                    sl_hit_count=metrics['sl_hit_count']
                )
                session.add(perf_metric)
                
                logger.info(f"💾 [PerformanceMonitor] Saved performance metrics for {metrics['date']}")
                
        except Exception as e:
            logger.error(f"❌ [PerformanceMonitor] Error saving metrics: {e}")
    
    def get_stats_for_telegram(self) -> Dict:
        """Get statistics for today only"""
        try:
            today = datetime.now().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            with db_manager.get_session() as session:
                signals = session.query(Signal).filter(
                    Signal.created_at >= today_start
                ).all()
                
                trades = session.query(Trade).filter(
                    Trade.exit_time >= today_start,
                    Trade.status == 'CLOSED'
                ).all()
                
                high_count = sum(1 for s in signals if s.priority == 'HIGH')
                medium_count = sum(1 for s in signals if s.priority == 'MEDIUM')
                low_count = sum(1 for s in signals if s.priority == 'LOW')
                
                win_count = sum(1 for t in trades if float(t.pnl_percent or 0) > 0)
                total_pnl = sum(float(t.pnl_percent or 0) for t in trades)
                win_rate = (win_count / len(trades)) * 100 if trades else 0
                
                tp1_count = sum(1 for t in trades if t.exit_reason == 'TAKE_PROFIT_1')
                tp2_count = sum(1 for t in trades if t.exit_reason == 'TAKE_PROFIT_2')
                sl_count = sum(1 for t in trades if t.exit_reason == 'STOP_LOSS')
                
                return {
                    'total_signals': len(signals),
                    'high_priority': high_count,
                    'medium_priority': medium_count,
                    'low_priority': low_count,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'tp1_count': tp1_count,
                    'tp2_count': tp2_count,
                    'sl_count': sl_count
                }
                
        except Exception as e:
            logger.error(f"❌ [PerformanceMonitor] Error getting stats: {e}")
            return {}
    
    def get_alltime_stats_for_telegram(self) -> Dict:
        """Get statistics for ALL TIME (all historical data)"""
        try:
            with db_manager.get_session() as session:
                # Get ALL signals (no date filter)
                signals = session.query(Signal).all()
                
                # Get ALL closed trades (no date filter)
                trades = session.query(Trade).filter(
                    Trade.status == 'CLOSED'
                ).all()
                
                # Priority breakdown
                high_count = sum(1 for s in signals if s.priority == 'HIGH')
                medium_count = sum(1 for s in signals if s.priority == 'MEDIUM')
                low_count = sum(1 for s in signals if s.priority == 'LOW')
                
                # Win/Loss metrics
                win_count = sum(1 for t in trades if float(t.pnl_percent or 0) > 0)
                loss_count = sum(1 for t in trades if float(t.pnl_percent or 0) <= 0)
                total_pnl = sum(float(t.pnl_percent or 0) for t in trades)
                win_rate = (win_count / len(trades)) * 100 if trades else 0
                
                # Exit reasons
                tp1_count = sum(1 for t in trades if t.exit_reason == 'TAKE_PROFIT_1')
                tp2_count = sum(1 for t in trades if t.exit_reason == 'TAKE_PROFIT_2')
                sl_count = sum(1 for t in trades if t.exit_reason == 'STOP_LOSS')
                
                # Average PnL
                avg_pnl = total_pnl / len(trades) if trades else 0
                
                # Average hold time
                hold_times = [t.hold_time_minutes for t in trades if t.hold_time_minutes]
                avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0
                
                # Get date range
                first_signal = session.query(Signal).order_by(Signal.created_at).first()
                first_date = first_signal.created_at.date() if first_signal else datetime.now().date()
                
                return {
                    'total_signals': len(signals),
                    'total_trades': len(trades),
                    'high_priority': high_count,
                    'medium_priority': medium_count,
                    'low_priority': low_count,
                    'win_count': win_count,
                    'loss_count': loss_count,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'avg_pnl': avg_pnl,
                    'avg_hold_time': avg_hold_time,
                    'tp1_count': tp1_count,
                    'tp2_count': tp2_count,
                    'sl_count': sl_count,
                    'first_date': first_date
                }
                
        except Exception as e:
            logger.error(f"❌ [PerformanceMonitor] Error getting alltime stats: {e}")
            return {}

performance_monitor = PerformanceMonitor()
