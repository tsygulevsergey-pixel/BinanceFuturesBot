"""
Fast Signal Tracker - monitors and closes signals with 100ms exit strategy
Uses in-memory cache for ultra-fast signal checks
Exit logic: imbalance reversal (aggressive protection), SL/TP
Note: IMBALANCE_NORMALIZED removed - let positions reach natural SL/TP targets
"""
import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime
from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.database import db_manager, Signal, Trade
from bot.modules.telegram_dispatcher import telegram_dispatcher
from decimal import Decimal


class FastSignalTracker:
    def __init__(self):
        """Initialize with empty in-memory cache"""
        self.open_signals_cache = {}  # {signal_id: signal_data}
        logger.info("🔧 [FastSignalTracker] Initialized with empty cache")
    
    async def sync_cache_from_db(self):
        """Synchronize open signals from PostgreSQL to in-memory cache"""
        try:
            logger.debug("🔄 [FastSignalTracker] Syncing cache from database...")
            
            with db_manager.get_session() as session:
                open_signals = session.query(Signal).filter(
                    Signal.status == 'OPEN'
                ).all()
                
                # Create new cache dictionary
                new_cache = {}
                for signal in open_signals:
                    signal_data = {
                        'id': signal.id,
                        'symbol': signal.symbol,
                        'direction': signal.direction,
                        'entry_price': float(signal.entry_price),
                        'stop_loss': float(signal.stop_loss),
                        'take_profit_1': float(signal.take_profit_1),
                        'take_profit_2': float(signal.take_profit_2),
                        'created_at': signal.created_at,
                        'telegram_message_id': signal.telegram_message_id
                    }
                    new_cache[signal.id] = signal_data
                
                # Update cache
                self.open_signals_cache = new_cache
                
                logger.info(
                    f"🔄 [FastSignalTracker] Cache synced: {len(self.open_signals_cache)} open signals"
                )
                
        except Exception as e:
            logger.error(f"❌ [FastSignalTracker] Error syncing cache from DB: {e}")
    
    async def check_signal_hybrid(self, signal_data: Dict) -> Optional[Dict]:
        """
        Check one signal with simplified exit logic
        
        Priority order:
        1. Opposite imbalance > 0.3 → IMBALANCE_REVERSED (aggressive protection)
        2. Stop-Loss hit → STOP_LOSS
        3. Take-Profit hit → TAKE_PROFIT_1/TAKE_PROFIT_2
        
        Note: IMBALANCE_NORMALIZED removed to prevent premature exits.
        Positions now run naturally to SL/TP unless real threat detected (reversal).
        
        IMPORTANT: This method monitors ALL open signals, even if their symbol
        was removed from the active universe. Signals continue being tracked
        as long as Redis data is available, and will close naturally when
        SL or TP is reached. If Redis data is unavailable (symbol removed),
        the check is skipped but the signal remains open.
        
        Returns:
            Dict with exit_reason and exit_price if signal should be closed
            None if signal should remain open
        """
        try:
            symbol = signal_data['symbol']
            direction = signal_data['direction']
            
            # Get imbalance from Redis
            # Note: Even if symbol was removed from universe, Redis data may still be available
            # for a short period, allowing SL/TP to execute naturally
            imbalance_data = redis_manager.get(f'imbalance:{symbol}')
            if imbalance_data is None:
                logger.debug(
                    f"⚠️ [FastSignalTracker] No imbalance data for {symbol}, skipping check "
                    f"(signal remains open, will retry in 100ms)"
                )
                return None
            
            current_imbalance = imbalance_data.get('imbalance', 0)
            
            # Get current price from Redis
            price_data = redis_manager.get(f'price:{symbol}')
            if price_data is None:
                logger.debug(
                    f"⚠️ [FastSignalTracker] No price data for {symbol}, skipping check "
                    f"(signal remains open, will retry in 100ms)"
                )
                return None
            
            current_price = float(price_data.get('mid', 0))
            if current_price == 0:
                logger.warning(f"⚠️ [FastSignalTracker] Invalid price for {symbol}")
                return None
            
            # Extract signal parameters
            entry_price = signal_data['entry_price']
            stop_loss = signal_data['stop_loss']
            tp1 = signal_data['take_profit_1']
            tp2 = signal_data['take_profit_2']
            
            # Priority 1: Imbalance reversed (aggressive protection only)
            # Only exit if imbalance REVERSES to opposite direction (real threat)
            if direction == 'LONG' and current_imbalance < -Config.IMBALANCE_EXIT_REVERSED:
                logger.info(
                    f"🚨 [FastSignalTracker] {symbol} LONG: Imbalance REVERSED to SELL "
                    f"({current_imbalance:.3f}) → EXIT"
                )
                return {
                    'signal_id': signal_data['id'],
                    'exit_reason': 'IMBALANCE_REVERSED',
                    'exit_price': current_price
                }
            elif direction == 'SHORT' and current_imbalance > Config.IMBALANCE_EXIT_REVERSED:
                logger.info(
                    f"🚨 [FastSignalTracker] {symbol} SHORT: Imbalance REVERSED to BUY "
                    f"({current_imbalance:.3f}) → EXIT"
                )
                return {
                    'signal_id': signal_data['id'],
                    'exit_reason': 'IMBALANCE_REVERSED',
                    'exit_price': current_price
                }
            
            # Priority 2 & 3: Price-based exits (SL/TP)
            # Let positions reach natural targets unless imbalance reverses
            exit_reason = None
            
            if direction == 'LONG':
                if current_price <= stop_loss:
                    exit_reason = 'STOP_LOSS'
                elif current_price >= tp2:
                    exit_reason = 'TAKE_PROFIT_2'
                elif current_price >= tp1:
                    exit_reason = 'TAKE_PROFIT_1'
            else:  # SHORT
                if current_price >= stop_loss:
                    exit_reason = 'STOP_LOSS'
                elif current_price <= tp2:
                    exit_reason = 'TAKE_PROFIT_2'
                elif current_price <= tp1:
                    exit_reason = 'TAKE_PROFIT_1'
            
            if exit_reason:
                logger.info(
                    f"⚡ [FastSignalTracker] {symbol} {direction}: {exit_reason} hit "
                    f"@ ${current_price:.4f} → EXIT"
                )
                return {
                    'signal_id': signal_data['id'],
                    'exit_reason': exit_reason,
                    'exit_price': current_price
                }
            
            # Signal should remain open
            return None
            
        except Exception as e:
            logger.error(
                f"❌ [FastSignalTracker] Error checking signal "
                f"{signal_data.get('id', 'unknown')}: {e}"
            )
            return None
    
    async def close_signals_batch(self, exit_signals: List[Dict]):
        """
        Batch close multiple signals
        
        Args:
            exit_signals: List of dicts with:
                - signal_id: str
                - exit_reason: str
                - exit_price: float
        """
        try:
            if not exit_signals:
                return
            
            logger.info(
                f"🏁 [FastSignalTracker] Batch closing {len(exit_signals)} signals"
            )
            
            with db_manager.get_session() as session:
                for exit_signal in exit_signals:
                    signal_id = exit_signal['signal_id']
                    exit_reason = exit_signal['exit_reason']
                    exit_price = exit_signal['exit_price']
                    
                    # Race condition protection: recheck status='OPEN'
                    signal = session.query(Signal).filter_by(
                        id=signal_id,
                        status='OPEN'
                    ).first()
                    
                    if not signal:
                        logger.warning(
                            f"⚠️ [FastSignalTracker] Signal {signal_id} already closed, skipping"
                        )
                        continue
                    
                    # Get signal data from cache
                    signal_data = self.open_signals_cache.get(signal_id)
                    if not signal_data:
                        logger.warning(
                            f"⚠️ [FastSignalTracker] Signal {signal_id} not in cache, "
                            f"using DB data"
                        )
                        signal_data = {
                            'entry_price': float(signal.entry_price),
                            'created_at': signal.created_at,
                            'telegram_message_id': signal.telegram_message_id
                        }
                    
                    entry_price = signal_data['entry_price']
                    
                    # Calculate PnL
                    if signal.direction == 'LONG':
                        pnl_percent = ((exit_price - entry_price) / entry_price) * 100
                    else:  # SHORT
                        pnl_percent = ((entry_price - exit_price) / entry_price) * 100
                    
                    # Calculate hold time
                    hold_time = int(
                        (datetime.now() - signal_data['created_at']).total_seconds() / 60
                    )
                    
                    # Update signal status
                    signal.status = 'CLOSED'
                    signal.updated_at = datetime.now()
                    
                    # Create trade record
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
                        f"🏁 [FastSignalTracker] Closed {signal.symbol} {signal.direction} "
                        f"@ ${exit_price:.4f} ({exit_reason}) "
                        f"PnL: {pnl_percent:+.2f}% Hold: {hold_time}min"
                    )
                    
                    # Send Telegram notification (non-blocking)
                    asyncio.create_task(
                        telegram_dispatcher.send_signal_update(
                            signal_id=signal.id,
                            symbol=signal.symbol,
                            exit_reason=exit_reason,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            pnl_percent=pnl_percent,
                            hold_time_minutes=hold_time,
                            original_message_id=signal_data.get('telegram_message_id')
                        )
                    )
                    
                    # Remove from cache
                    if signal_id in self.open_signals_cache:
                        del self.open_signals_cache[signal_id]
                        logger.debug(
                            f"🗑️ [FastSignalTracker] Removed {signal_id} from cache"
                        )
                
                # Commit all changes
                session.commit()
                logger.info(
                    f"✅ [FastSignalTracker] Batch close completed: "
                    f"{len(exit_signals)} signals processed"
                )
                
        except Exception as e:
            logger.error(f"❌ [FastSignalTracker] Error in batch close: {e}")


# Singleton instance
fast_signal_tracker = FastSignalTracker()
