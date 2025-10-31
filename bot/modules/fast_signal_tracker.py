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
        """Initialize with empty in-memory cache and persistence counters"""
        self.open_signals_cache = {}  # {signal_id: signal_data}
        self.reversal_counters = {}   # {signal_id: consecutive_reversed_samples_count}
        self.partial_close_cache = {}  # {signal_id: {'status': 'NONE', 'breakeven_moved': False, 'current_sl': None, 'tp1_pnl': None}}
        logger.info("🔧 [FastSignalTracker] Initialized with empty cache, persistence counters, and partial close cache")
    
    async def sync_cache_from_db(self):
        """Synchronize open signals from PostgreSQL to in-memory cache"""
        try:
            logger.debug("🔄 [FastSignalTracker] Syncing cache from database...")
            
            with db_manager.get_session() as session:
                open_signals = session.query(Signal).filter(
                    Signal.status == 'OPEN'
                ).all()
                
                # Create new cache dictionaries
                new_cache = {}
                new_partial_close_cache = {}
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
                        'telegram_message_id': signal.telegram_message_id,
                        'partial_close_status': getattr(signal, 'partial_close_status', 'NONE'),
                        'breakeven_moved': getattr(signal, 'breakeven_moved', False),
                        'current_stop_loss': float(getattr(signal, 'current_stop_loss', None) or 0) or None,
                        'tp1_pnl': float(getattr(signal, 'tp1_pnl', None) or 0) or None
                    }
                    new_cache[signal.id] = signal_data
                    
                    # Initialize partial close cache from DB data
                    new_partial_close_cache[signal.id] = {
                        'status': getattr(signal, 'partial_close_status', None) or 'NONE',
                        'breakeven_moved': getattr(signal, 'breakeven_moved', None) or False,
                        'current_sl': float(getattr(signal, 'current_stop_loss', None) or 0) or float(signal.stop_loss),
                        'tp1_pnl': float(getattr(signal, 'tp1_pnl', None) or 0) or None
                    }
                
                # Update caches
                self.open_signals_cache = new_cache
                self.partial_close_cache = new_partial_close_cache
                
                # Clean up reversal counters for closed signals
                # Keep only counters for signals that are still open
                closed_signal_ids = set(self.reversal_counters.keys()) - set(new_cache.keys())
                for signal_id in closed_signal_ids:
                    del self.reversal_counters[signal_id]
                
                logger.info(
                    f"🔄 [FastSignalTracker] Cache synced: {len(self.open_signals_cache)} open signals, "
                    f"{len(self.reversal_counters)} active reversal counters, "
                    f"{len(self.partial_close_cache)} partial close states"
                )
                
        except Exception as e:
            logger.error(f"❌ [FastSignalTracker] Error syncing cache from DB: {e}")
    
    async def check_signal_hybrid(self, signal_data: Dict) -> Optional[Dict]:
        """
        Check one signal with TWO-LAYER protection against premature exits
        
        Priority order:
        1. Stop-Loss hit → STOP_LOSS (always active)
        2. Take-Profit hit → TAKE_PROFIT_1/TAKE_PROFIT_2 (always active)
        3. Opposite imbalance > 0.4 → IMBALANCE_REVERSED (with 2-layer protection)
        
        TWO-LAYER PROTECTION:
        - Layer 1 (Time): No exits in first 30 seconds (MIN_HOLD_TIME)
        - Layer 2 (Persistence): After 30s, require 50 consecutive samples (5 sec) 
          of sustained reversal before exit
        
        This prevents exits on temporary imbalance spikes (noise) and allows 
        positions to reach TP1/TP2 targets naturally.
        
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
            
            # Calculate hold time
            created_at = signal_data['created_at']
            hold_time = (datetime.now() - created_at).total_seconds()
            
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
            signal_id = signal_data['id']
            entry_price = signal_data['entry_price']
            stop_loss = signal_data['stop_loss']
            tp1 = signal_data['take_profit_1']
            tp2 = signal_data['take_profit_2']
            
            # Get partial close status from cache (with fallback defaults)
            partial_status = self.partial_close_cache.get(signal_id, {}).get('status', 'NONE')
            breakeven_moved = self.partial_close_cache.get(signal_id, {}).get('breakeven_moved', False)
            current_sl = self.partial_close_cache.get(signal_id, {}).get('current_sl', stop_loss)
            
            # Initialize partial close cache if not exists
            if signal_id not in self.partial_close_cache:
                self.partial_close_cache[signal_id] = {
                    'status': 'NONE',
                    'breakeven_moved': False,
                    'current_sl': stop_loss,
                    'tp1_pnl': None
                }
            
            # NEW EXIT LOGIC ORDER (following architect's recommendation)
            # Priority 1: TP2 hit (only if TP1 already closed) - handles edge case when price jumps through TP1
            if partial_status == 'TP1_CLOSED' and (
                (direction == 'LONG' and current_price >= tp2) or 
                (direction == 'SHORT' and current_price <= tp2)
            ):
                # Close remaining 50%
                if direction == 'LONG':
                    tp2_pnl = (tp2 - entry_price) / entry_price * 0.5
                else:  # SHORT
                    tp2_pnl = (entry_price - tp2) / entry_price * 0.5
                
                # Fetch tp1_pnl from cache
                tp1_pnl = self.partial_close_cache[signal_id].get('tp1_pnl', 0)
                total_pnl = tp1_pnl + tp2_pnl
                
                logger.info(
                    f"🎯🎯 [FastSignalTracker] TP2 HIT! {symbol} {direction}: "
                    f"Closed remaining 50% @ ${current_price:.4f}, "
                    f"Total PnL: +{total_pnl*100:.2f}% (hold: {hold_time:.1f}s)"
                )
                
                return {
                    'signal_id': signal_id,
                    'exit_reason': 'TAKE_PROFIT_2',
                    'exit_price': current_price,
                    'total_pnl': total_pnl,
                    'tp2_pnl': tp2_pnl,
                    'partial_close': True
                }
            
            # Priority 2: TP1 hit (first time) - PARTIAL CLOSE (50%)
            if partial_status == 'NONE' and (
                (direction == 'LONG' and current_price >= tp1) or 
                (direction == 'SHORT' and current_price <= tp1)
            ):
                # Close 50%, move SL to breakeven
                if direction == 'LONG':
                    tp1_pnl = (tp1 - entry_price) / entry_price * 0.5
                else:  # SHORT
                    tp1_pnl = (entry_price - tp1) / entry_price * 0.5
                
                new_sl = entry_price  # Breakeven
                
                logger.info(
                    f"🎯 [FastSignalTracker] TP1 HIT! {symbol} {direction}: "
                    f"Closed 50% @ ${current_price:.4f} (+{tp1_pnl*100:.2f}%), "
                    f"SL → Breakeven (hold: {hold_time:.1f}s)"
                )
                
                # Update cache immediately (DB update happens in close_signals_batch)
                self.partial_close_cache[signal_id] = {
                    'status': 'TP1_CLOSED',
                    'breakeven_moved': True,
                    'current_sl': new_sl,
                    'tp1_pnl': tp1_pnl
                }
                
                return {
                    'signal_id': signal_id,
                    'exit_reason': 'TAKE_PROFIT_1_PARTIAL',
                    'exit_price': current_price,
                    'tp1_pnl': tp1_pnl,
                    'new_sl': new_sl,
                    'partial_close': True
                }
            
            # Priority 3: Stop-Loss (with breakeven adjustment)
            if (direction == 'LONG' and current_price <= current_sl) or (direction == 'SHORT' and current_price >= current_sl):
                if partial_status == 'TP1_CLOSED':
                    # Breakeven SL hit - protected profit
                    tp1_pnl = self.partial_close_cache[signal_id].get('tp1_pnl', 0)
                    tp2_pnl = 0.0  # Breakeven on remaining 50%
                    total_pnl = tp1_pnl + tp2_pnl
                    
                    logger.info(
                        f"🛡️ [FastSignalTracker] SL BREAKEVEN! {symbol} {direction}: "
                        f"Closed remaining 50% @ ${current_price:.4f} (entry), "
                        f"Total PnL: +{total_pnl*100:.2f}% (hold: {hold_time:.1f}s)"
                    )
                    
                    return {
                        'signal_id': signal_id,
                        'exit_reason': 'STOP_LOSS_BREAKEVEN',
                        'exit_price': current_price,
                        'total_pnl': total_pnl,
                        'tp2_pnl': tp2_pnl,
                        'partial_close': True
                    }
                else:
                    # Full position SL (initial SL hit)
                    if direction == 'LONG':
                        total_pnl = (current_price - entry_price) / entry_price
                    else:  # SHORT
                        total_pnl = (entry_price - current_price) / entry_price
                    
                    logger.info(
                        f"🛑 [FastSignalTracker] STOP LOSS! {symbol} {direction}: "
                        f"Full position closed @ ${current_price:.4f}, "
                        f"PnL: {total_pnl*100:.2f}% (hold: {hold_time:.1f}s)"
                    )
                    
                    return {
                        'signal_id': signal_id,
                        'exit_reason': 'STOP_LOSS',
                        'exit_price': current_price,
                        'total_pnl': total_pnl,
                        'partial_close': False
                    }
            
            # Priority 4: Imbalance reversed with PERSISTENCE FILTER
            # After MIN_HOLD_TIME, require SUSTAINED reversal (50 consecutive samples = 5 seconds)
            # This prevents exits on temporary imbalance spikes
            
            # Initialize persistence counter if not exists
            if signal_id not in self.reversal_counters:
                self.reversal_counters[signal_id] = 0
            
            # Check if we're past the minimum hold time
            if hold_time >= Config.MIN_HOLD_TIME_SECONDS:
                # Check if imbalance is currently reversed
                imbalance_is_reversed = (
                    (direction == 'LONG' and current_imbalance < -Config.IMBALANCE_EXIT_REVERSED) or
                    (direction == 'SHORT' and current_imbalance > Config.IMBALANCE_EXIT_REVERSED)
                )
                
                if imbalance_is_reversed:
                    # Increment persistence counter
                    self.reversal_counters[signal_id] += 1
                    counter = self.reversal_counters[signal_id]
                    
                    # Check if we've reached persistence threshold
                    if counter >= Config.IMBALANCE_REVERSAL_PERSISTENCE_SAMPLES:
                        logger.info(
                            f"🚨 [FastSignalTracker] {symbol} {direction}: Imbalance REVERSED "
                            f"({current_imbalance:.3f}) CONFIRMED for {counter} samples "
                            f"(hold: {hold_time:.1f}s) → EXIT"
                        )
                        # Reset counter before exit (cleanup)
                        self.reversal_counters[signal_id] = 0
                        return {
                            'signal_id': signal_id,
                            'exit_reason': 'IMBALANCE_REVERSED',
                            'exit_price': current_price
                        }
                    else:
                        # Still building confirmation (logged at DEBUG to avoid spam every 100ms)
                        logger.debug(
                            f"📊 [FastSignalTracker] {symbol} {direction}: Reversal confirmation "
                            f"building {counter}/{Config.IMBALANCE_REVERSAL_PERSISTENCE_SAMPLES} "
                            f"(imbalance: {current_imbalance:.3f}, hold: {hold_time:.1f}s)"
                        )
                else:
                    # Imbalance is NOT reversed - reset counter if it was building
                    if self.reversal_counters[signal_id] > 0:
                        logger.info(
                            f"✅ [FastSignalTracker] {symbol} {direction}: Reversal dissipated, "
                            f"resetting counter from {self.reversal_counters[signal_id]} "
                            f"(imbalance: {current_imbalance:.3f}, hold: {hold_time:.1f}s)"
                        )
                        self.reversal_counters[signal_id] = 0
            else:
                # Still within MIN_HOLD_TIME protection window (logged at DEBUG to avoid spam)
                if direction == 'LONG' and current_imbalance < -Config.IMBALANCE_EXIT_REVERSED:
                    logger.debug(
                        f"⏳ [FastSignalTracker] {symbol} LONG: Imbalance reversed "
                        f"({current_imbalance:.3f}) but PROTECTED (hold: {hold_time:.1f}s < "
                        f"{Config.MIN_HOLD_TIME_SECONDS}s) → KEEPING OPEN"
                    )
                elif direction == 'SHORT' and current_imbalance > Config.IMBALANCE_EXIT_REVERSED:
                    logger.debug(
                        f"⏳ [FastSignalTracker] {symbol} SHORT: Imbalance reversed "
                        f"({current_imbalance:.3f}) but PROTECTED (hold: {hold_time:.1f}s < "
                        f"{Config.MIN_HOLD_TIME_SECONDS}s) → KEEPING OPEN"
                    )
            
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
        Batch close multiple signals with support for partial closes
        
        Args:
            exit_signals: List of dicts with:
                - signal_id: str
                - exit_reason: str ('TAKE_PROFIT_1_PARTIAL', 'TAKE_PROFIT_2', 'STOP_LOSS_BREAKEVEN', 'STOP_LOSS', 'IMBALANCE_REVERSED')
                - exit_price: float
                - tp1_pnl: float (optional, for partial close)
                - tp2_pnl: float (optional, for partial close)
                - total_pnl: float (optional, for partial close)
                - new_sl: float (optional, for TP1 partial close)
                - partial_close: bool (optional, indicates if this is a partial close)
        """
        try:
            if not exit_signals:
                return
            
            logger.info(
                f"🏁 [FastSignalTracker] Batch processing {len(exit_signals)} signal exits"
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
                    
                    # Calculate hold time
                    hold_time = int(
                        (datetime.now() - signal_data['created_at']).total_seconds() / 60
                    )
                    
                    # Handle different exit reasons
                    if exit_reason == 'TAKE_PROFIT_1_PARTIAL':
                        # TP1 hit - PARTIAL CLOSE (50%), keep signal OPEN
                        tp1_pnl = exit_signal.get('tp1_pnl', 0)
                        new_sl = exit_signal.get('new_sl', entry_price)
                        
                        # Update signal with TP1 data
                        signal.tp1_hit_price = Decimal(str(exit_price))
                        signal.tp1_hit_time = datetime.now()
                        signal.tp1_pnl = Decimal(str(tp1_pnl))
                        signal.partial_close_status = 'TP1_CLOSED'
                        signal.breakeven_moved = True
                        signal.current_stop_loss = Decimal(str(new_sl))
                        signal.updated_at = datetime.now()
                        # Keep status='OPEN' - signal remains active
                        
                        logger.info(
                            f"🎯 [FastSignalTracker] TP1 PARTIAL: {signal.symbol} {signal.direction} "
                            f"@ ${exit_price:.4f} (+{tp1_pnl*100:.2f}%), SL→${new_sl:.4f} (breakeven), "
                            f"Hold: {hold_time}min, Signal remains OPEN"
                        )
                        
                        # Send Telegram notification (non-blocking)
                        asyncio.create_task(
                            telegram_dispatcher.send_signal_update(
                                signal_id=signal.id,
                                symbol=signal.symbol,
                                exit_reason='TAKE_PROFIT_1_PARTIAL',
                                entry_price=entry_price,
                                exit_price=exit_price,
                                pnl_percent=tp1_pnl * 100,
                                hold_time_minutes=hold_time,
                                original_message_id=signal_data.get('telegram_message_id')
                            )
                        )
                        
                        # DON'T remove from cache - signal remains open
                        
                    elif exit_reason in ['TAKE_PROFIT_2', 'STOP_LOSS_BREAKEVEN']:
                        # TP2 or breakeven SL hit - FULLY CLOSE (after partial close)
                        tp2_pnl = exit_signal.get('tp2_pnl', 0)
                        total_pnl = exit_signal.get('total_pnl', 0)
                        
                        # Update signal with TP2 data and close
                        signal.tp2_hit_price = Decimal(str(exit_price))
                        signal.tp2_hit_time = datetime.now()
                        signal.tp2_pnl = Decimal(str(tp2_pnl))
                        signal.partial_close_status = 'FULLY_CLOSED'
                        signal.status = 'CLOSED'
                        signal.updated_at = datetime.now()
                        
                        # Create trade record with partial close data
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
                            pnl_percent=total_pnl * 100,
                            tp1_hit_price=signal.tp1_hit_price,
                            tp1_hit_time=signal.tp1_hit_time,
                            tp1_pnl=signal.tp1_pnl,
                            tp2_hit_price=Decimal(str(exit_price)),
                            tp2_hit_time=datetime.now(),
                            tp2_pnl=Decimal(str(tp2_pnl)),
                            partial_close_status='FULLY_CLOSED',
                            hold_time_minutes=hold_time,
                            status='CLOSED',
                            entry_time=signal.created_at,
                            exit_time=datetime.now()
                        )
                        session.add(trade)
                        
                        logger.info(
                            f"🎯🎯 [FastSignalTracker] {exit_reason}: {signal.symbol} {signal.direction} "
                            f"@ ${exit_price:.4f}, Total PnL: {total_pnl*100:+.2f}%, "
                            f"Hold: {hold_time}min, FULLY CLOSED"
                        )
                        
                        # Send Telegram notification (non-blocking)
                        asyncio.create_task(
                            telegram_dispatcher.send_signal_update(
                                signal_id=signal.id,
                                symbol=signal.symbol,
                                exit_reason=exit_reason,
                                entry_price=entry_price,
                                exit_price=exit_price,
                                pnl_percent=total_pnl * 100,
                                hold_time_minutes=hold_time,
                                original_message_id=signal_data.get('telegram_message_id')
                            )
                        )
                        
                        # Remove from cache - signal is fully closed
                        if signal_id in self.open_signals_cache:
                            del self.open_signals_cache[signal_id]
                        if signal_id in self.partial_close_cache:
                            del self.partial_close_cache[signal_id]
                        logger.debug(
                            f"🗑️ [FastSignalTracker] Removed {signal_id} from all caches"
                        )
                        
                    else:
                        # Regular full close (STOP_LOSS, IMBALANCE_REVERSED)
                        # Calculate PnL
                        if exit_reason == 'STOP_LOSS' or exit_reason == 'IMBALANCE_REVERSED':
                            if signal.direction == 'LONG':
                                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
                            else:  # SHORT
                                pnl_percent = ((entry_price - exit_price) / entry_price) * 100
                        else:
                            pnl_percent = 0
                        
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
                            f"🏁 [FastSignalTracker] {exit_reason}: {signal.symbol} {signal.direction} "
                            f"@ ${exit_price:.4f}, PnL: {pnl_percent:+.2f}%, "
                            f"Hold: {hold_time}min, FULLY CLOSED"
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
                        if signal_id in self.partial_close_cache:
                            del self.partial_close_cache[signal_id]
                        logger.debug(
                            f"🗑️ [FastSignalTracker] Removed {signal_id} from all caches"
                        )
                
                # Commit all changes
                session.commit()
                logger.info(
                    f"✅ [FastSignalTracker] Batch processing completed: "
                    f"{len(exit_signals)} signal exits processed"
                )
                
        except Exception as e:
            logger.error(f"❌ [FastSignalTracker] Error in batch close: {e}")


# Singleton instance
fast_signal_tracker = FastSignalTracker()
