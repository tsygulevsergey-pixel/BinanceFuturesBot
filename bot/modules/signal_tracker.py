"""
Signal Tracker - monitors and closes signals every minute
Checks if price hit SL, TP1, or TP2 levels
Updates database and sends Telegram notifications
"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.database import db_manager, Signal, Trade
from bot.modules.telegram_dispatcher import telegram_dispatcher
from decimal import Decimal

class SignalTracker:
    def __init__(self):
        logger.info("🔧 [SignalTracker] Initialized")
    
    async def check_signals(self):
        try:
            logger.debug("🔍 [SignalTracker] Checking open signals...")
            
            with db_manager.get_session() as session:
                open_signals = session.query(Signal).filter(
                    Signal.status == 'OPEN'
                ).all()
                
                if not open_signals:
                    logger.debug("📭 [SignalTracker] No open signals to track")
                    return
                
                logger.info(f"📊 [SignalTracker] Tracking {len(open_signals)} open signals")
                
                for signal in open_signals:
                    await self.check_signal(signal, session)
                    
        except Exception as e:
            logger.error(f"❌ [SignalTracker] Error checking signals: {e}")
    
    async def check_signal(self, signal: Signal, session):
        try:
            # Get real-time price from Redis (populated by bookTicker WebSocket)
            price_data = redis_manager.get(f'price:{signal.symbol}')
            
            if not price_data:
                logger.warning(f"⚠️ [SignalTracker] No price data in Redis for {signal.symbol}")
                return
            
            # Use mid price (average of best bid/ask) for more accurate tracking
            current_price = float(price_data.get('mid', 0))
            
            if current_price == 0:
                logger.warning(f"⚠️ [SignalTracker] Invalid price for {signal.symbol}")
                return
            
            entry_price = float(signal.entry_price)
            stop_loss = float(signal.stop_loss)
            tp1 = float(signal.take_profit_1)
            tp2 = float(signal.take_profit_2)
            
            exit_reason = None
            exit_price = current_price
            
            if signal.direction == 'LONG':
                if current_price <= stop_loss:
                    exit_reason = 'STOP_LOSS'
                elif current_price >= tp2:
                    exit_reason = 'TAKE_PROFIT_2'
                elif current_price >= tp1:
                    exit_reason = 'TAKE_PROFIT_1'
            else:
                if current_price >= stop_loss:
                    exit_reason = 'STOP_LOSS'
                elif current_price <= tp2:
                    exit_reason = 'TAKE_PROFIT_2'
                elif current_price <= tp1:
                    exit_reason = 'TAKE_PROFIT_1'
            
            if exit_reason:
                await self.close_signal(signal, exit_reason, exit_price, session)
            
        except Exception as e:
            logger.error(f"❌ [SignalTracker] Error checking signal {signal.id}: {e}")
    
    async def close_signal(self, signal: Signal, exit_reason: str, exit_price: float, session):
        try:
            entry_price = float(signal.entry_price)
            
            if signal.direction == 'LONG':
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
            else:
                pnl_percent = ((entry_price - exit_price) / entry_price) * 100
            
            hold_time = int((datetime.now() - signal.created_at).total_seconds() / 60)
            
            signal.status = 'CLOSED'
            signal.updated_at = datetime.now()
            
            trade = Trade(
                signal_id=signal.id,
                symbol=signal.symbol,
                direction=signal.direction,
                entry_price=signal.entry_price,
                exit_price=Decimal(str(exit_price)),
                stop_loss=signal.stop_loss,
                take_profit_1=signal.take_profit_1,
                take_profit_2=signal.take_profit_2,
                exit_reason=exit_reason,
                pnl_percent=pnl_percent,
                hold_time_minutes=hold_time,
                status='CLOSED',
                entry_time=signal.created_at,
                exit_time=datetime.now()
            )
            session.add(trade)
            
            logger.info(
                f"🏁 [SignalTracker] Closed signal: {signal.symbol} {signal.direction} "
                f"@ ${exit_price:.4f} ({exit_reason}) PnL: {pnl_percent:+.2f}% Hold: {hold_time}min"
            )
            
            await telegram_dispatcher.send_signal_update(
                signal_id=signal.id,
                symbol=signal.symbol,
                exit_reason=exit_reason,
                entry_price=entry_price,
                exit_price=exit_price,
                pnl_percent=pnl_percent,
                hold_time_minutes=hold_time,
                original_message_id=signal.telegram_message_id
            )
            
        except Exception as e:
            logger.error(f"❌ [SignalTracker] Error closing signal {signal.id}: {e}")

signal_tracker = SignalTracker()
