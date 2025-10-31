"""
Main bot file - orchestrates all modules for 24/7 operation
Scans universe every 6 hours, collects data via WebSocket, generates signals
Tracks signals every minute, sends notifications to Telegram
"""
import asyncio
import sys
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.utils.binance_client import binance_client
from bot.database import db_manager, Signal
from bot.modules import (
    universe_selector,
    data_collector,
    orderbook_analyzer,
    trade_flow_analyzer,
    SignalGenerator,
    risk_manager,
    telegram_dispatcher,
    performance_monitor
)
from bot.modules.fast_signal_tracker import fast_signal_tracker
from bot.telegram_bot import telegram_bot_handler

class BinanceFuturesScanner:
    def __init__(self):
        self.running = False
        self.last_universe_scan = None
        self.signal_generator = None
        
        logger.info("="*80)
        logger.info("🚀 Binance Futures Scanner Bot Initializing...")
        logger.info("="*80)
    
    async def initialize(self):
        try:
            logger.info("🔧 [Main] Starting initialization...")
            
            db_manager.init_sync_db()
            await db_manager.init_async_pool()
            
            self.signal_generator = SignalGenerator(db_manager.async_pool)
            logger.info("✅ [Main] SignalGenerator initialized with db_pool")
            
            redis_manager.connect()
            
            binance_client.init_sync_client()
            await binance_client.init_async_session()
            
            await telegram_dispatcher.initialize()
            
            await telegram_bot_handler.start_bot()
            
            await telegram_dispatcher.send_startup_message()
            
            logger.info("✅ [Main] Initialization complete!")
            
        except Exception as e:
            logger.error(f"❌ [Main] Initialization failed: {e}")
            raise
    
    async def run(self):
        try:
            self.running = True
            
            logger.info("🚀 [Main] Starting main loop...")
            
            await self.scan_universe_initial()
            
            # Preload historical klines for ATR calculation (eliminates 20min wait!)
            active_symbols = universe_selector.get_active_symbols()
            if active_symbols:
                await self.preload_historical_klines(active_symbols)
                logger.info(f"🚀 [Main] Starting DataCollector for {len(active_symbols)} symbols...")
            
            tasks = [
                self.universe_scan_loop(),
                self.signal_generation_loop(),
                self.fast_signal_tracking_loop(),  # NEW: 100ms hybrid tracking
                self.metrics_update_loop(),
                data_collector.start_collecting(active_symbols) if active_symbols else asyncio.sleep(0)
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("⚠️ [Main] Received keyboard interrupt, shutting down...")
            await self.shutdown()
        except Exception as e:
            logger.error(f"❌ [Main] Main loop error: {e}")
            await self.shutdown()
    
    async def scan_universe_initial(self):
        try:
            logger.info("🔍 [Main] Performing initial universe scan...")
            
            symbols = await universe_selector.scan_universe()
            
            if symbols:
                await telegram_dispatcher.send_universe_update(len(symbols), symbols)
                self.last_universe_scan = datetime.now()
                
                logger.info(f"✅ [Main] Initial scan complete, selected {len(symbols)} symbols")
            else:
                logger.warning("⚠️ [Main] Initial universe scan returned no symbols")
                
        except Exception as e:
            logger.error(f"❌ [Main] Error in initial universe scan: {e}")
    
    async def preload_historical_klines(self, symbols: list):
        """
        Preload last 30 1m klines for each symbol from Binance API
        This eliminates the 20-minute wait for ATR calculation on bot restart
        """
        try:
            logger.info(f"📥 [Main] Preloading historical klines for {len(symbols)} symbols...")
            
            from bot.database.models import Kline as KlineModel
            from decimal import Decimal
            
            total_loaded = 0
            failed = 0
            
            for symbol in symbols:
                try:
                    # Fetch last 30 1m candles from Binance
                    klines = await binance_client.get_klines(symbol, '1m', limit=30)
                    
                    if not klines:
                        logger.warning(f"⚠️ [Main] No klines data for {symbol}")
                        failed += 1
                        continue
                    
                    # Insert into database
                    with db_manager.get_session() as session:
                        for kline in klines:
                            # Binance kline format: [timestamp, open, high, low, close, volume, ...]
                            kline_obj = KlineModel(
                                symbol=symbol,
                                interval='1m',
                                timestamp=datetime.fromtimestamp(kline[0] / 1000),  # Convert ms to seconds
                                open=Decimal(str(kline[1])),
                                high=Decimal(str(kline[2])),
                                low=Decimal(str(kline[3])),
                                close=Decimal(str(kline[4])),
                                volume=Decimal(str(kline[5]))
                            )
                            session.merge(kline_obj)  # Use merge to avoid duplicates
                        
                        total_loaded += len(klines)
                    
                    logger.debug(f"✅ [Main] Loaded {len(klines)} klines for {symbol}")
                    
                except Exception as e:
                    logger.error(f"❌ [Main] Failed to load klines for {symbol}: {e}")
                    failed += 1
                    continue
            
            logger.info(f"✅ [Main] Preloaded {total_loaded} klines for {len(symbols) - failed}/{len(symbols)} symbols")
            
        except Exception as e:
            logger.error(f"❌ [Main] Error preloading historical klines: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def universe_scan_loop(self):
        """
        Rescan universe every hour to update active symbols list.
        
        IMPORTANT: Open signals for symbols that are removed from universe
        are NOT automatically closed. They continue to be monitored by
        FastSignalTracker and will close naturally when SL or TP is hit.
        """
        while self.running:
            try:
                await asyncio.sleep(Config.UNIVERSE_RESCAN_INTERVAL)
                
                logger.info("🔄 [Main] Rescanning universe...")
                logger.info(
                    "ℹ️ [Main] Note: Open signals for removed symbols will continue monitoring "
                    "until SL/TP is reached"
                )
                
                symbols = await universe_selector.scan_universe()
                
                if symbols:
                    await telegram_dispatcher.send_universe_update(len(symbols), symbols)
                    self.last_universe_scan = datetime.now()
                    
                    logger.info(f"✅ [Main] Universe rescan complete, {len(symbols)} symbols")
                
            except Exception as e:
                logger.error(f"❌ [Main] Error in universe scan loop: {e}")
                await asyncio.sleep(300)
    
    async def signal_generation_loop(self):
        logger.info("🎯 [Main] Starting signal generation loop...")
        
        while self.running:
            try:
                active_symbols = universe_selector.get_active_symbols()
                
                if not active_symbols:
                    logger.warning("⚠️ [Main] No active symbols, waiting...")
                    await asyncio.sleep(30)
                    continue
                
                logger.info(f"🔍 [Main] Analyzing ALL {len(active_symbols)} symbols for signals...")
                
                signals_generated = 0
                # Analyze ALL symbols that passed filters (no artificial limits!)
                for symbol in active_symbols:
                    result = await self.check_and_generate_signal(symbol, active_symbols)
                    if result:
                        signals_generated += 1
                    # No delay needed - all data comes from Redis (no Binance API calls!)
                
                logger.info(f"✅ [Main] Completed signal check for {len(active_symbols)} symbols - Generated {signals_generated} signals")
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ [Main] Error in signal generation loop: {e}")
                await asyncio.sleep(60)
    
    async def check_and_generate_signal(self, symbol: str, active_symbols: list = []):
        try:
            orderbook = redis_manager.get(f'orderbook:{symbol}')
            if not orderbook:
                logger.debug(f"⚠️ [Main] No orderbook data for {symbol}")
                return
            
            trade_flow = redis_manager.get(f'trade_flow:{symbol}')
            if not trade_flow:
                logger.debug(f"⚠️ [Main] No trade_flow data for {symbol}")
                return
            
            imbalance = orderbook_analyzer.calculate_imbalance(
                orderbook.get('bids', []),
                orderbook.get('asks', [])
            )
            
            orderbook_data = {
                'imbalance': imbalance
            }
            
            # Log first 3 symbols for diagnostics
            symbol_index = active_symbols.index(symbol) if symbol in active_symbols else -1
            if symbol_index < 3:
                logger.info(
                    f"📊 [DIAGNOSTIC {symbol}] "
                    f"imb={imbalance:.3f}, "
                    f"large_buys={trade_flow.get('large_buys', 0)}, "
                    f"large_sells={trade_flow.get('large_sells', 0)}"
                )
            
            # OPTIMIZATION: Quick pre-check (only imbalance + large_trades, no extra API calls)
            quick_long = self.signal_generator.quick_check_long(orderbook_data, trade_flow)
            quick_short = self.signal_generator.quick_check_short(orderbook_data, trade_flow)
            
            if not quick_long and not quick_short:
                # Log first 3 quick_check failures for diagnostics
                if symbol_index < 3:
                    logger.info(
                        f"❌ [DIAGNOSTIC {symbol}] Failed quick_check: "
                        f"imb={imbalance:.3f} (need >0.28 for LONG or <-0.28 for SHORT), "
                        f"large_buys={trade_flow.get('large_buys', 0)}, "
                        f"large_sells={trade_flow.get('large_sells', 0)} (need ≥3)"
                    )
                return
            
            # Passed quick check! Now calculate volume_intensity with historical comparison
            current_volume_per_minute = trade_flow.get('volume_per_minute', 0)
            
            # Get average volume from 15m kline data (if available)
            kline_15m = redis_manager.get(f'kline_15m:{symbol}')
            if kline_15m:
                avg_volume_15m = kline_15m.get('volume', 0) / 15  # Convert 15m to per-minute
                # volume_intensity = current / average (should be > 1.8x for signal)
                volume_intensity = current_volume_per_minute / avg_volume_15m if avg_volume_15m > 0 else 0
                logger.debug(
                    f"📈 [{symbol}] volume_intensity={volume_intensity:.2f} "
                    f"(current={current_volume_per_minute:,.0f}/min, avg={avg_volume_15m:,.0f}/min)"
                )
            else:
                # Fallback: If no 15m klines, use a more realistic baseline
                # Assume minimum liquid symbol has ~100K volume per minute
                # This is still strict but not impossible
                baseline_volume = 100_000
                volume_intensity = current_volume_per_minute / baseline_volume
                logger.warning(
                    f"⚠️ [{symbol}] No 15m kline data, using fallback baseline (100K/min): "
                    f"volume_intensity={volume_intensity:.2f} (current={current_volume_per_minute:,.0f}/min)"
                )
            
            trade_flow['volume_intensity'] = volume_intensity
            
            # Get ACCURATE price from bookTicker (NOT from orderbook deltas!)
            price_info = redis_manager.get(f'price:{symbol}')
            if not price_info:
                # Fallback to mid-price if bookTicker not available yet
                return
            
            price = price_info.get('mid', 0)  # Use mid price (average of bid/ask)
            vwap = trade_flow.get('vwap', price)
            
            price_data = {
                'price': price,
                'vwap': vwap,
                'rsi': 50,
                'near_support': False,
                'near_resistance': False
            }
            
            # Full check with volume_intensity and VWAP (NOW ASYNC!)
            can_long, long_conditions = await self.signal_generator.check_long_conditions(
                symbol,
                orderbook_data,
                trade_flow,
                price_data,
                orderbook
            )
            
            can_short, short_conditions = await self.signal_generator.check_short_conditions(
                symbol,
                orderbook_data,
                trade_flow,
                price_data,
                orderbook
            )
            
            # Debug log for EVERY 10th symbol to see why signals aren't generated
            symbol_index = active_symbols.index(symbol) if symbol in active_symbols else -1
            if symbol_index % 10 == 0:  # Log every 10th symbol
                avg_vol_info = f"avg={kline_15m.get('volume', 0)/15:,.0f}" if kline_15m else "no kline"
                logger.info(f"📊 [DEBUG {symbol}] imb={imbalance:.3f}, large_buys={trade_flow.get('large_buys', 0)}, large_sells={trade_flow.get('large_sells', 0)}, vol_int={volume_intensity:.2f} (current={current_volume_per_minute:,.0f}, {avg_vol_info}), vwap=${vwap:.2f}, price=${price:.2f}")
                if not can_long and not can_short:
                    failed_long = [k for k, v in long_conditions.get('required', {}).items() if not v]
                    failed_short = [k for k, v in short_conditions.get('required', {}).items() if not v]
                    logger.info(f"📊 [DEBUG {symbol}] LONG failed: {failed_long}, SHORT failed: {failed_short}")
            
            direction = None
            dynamic_data = None
            if can_long:
                direction = 'LONG'
                dynamic_data = long_conditions
            elif can_short:
                direction = 'SHORT'
                dynamic_data = short_conditions
            
            if not direction or not dynamic_data:
                return
            
            signal_data = self.signal_generator.generate_signal(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                orderbook_data=orderbook_data,
                trade_flow=trade_flow,
                price_data=price_data,
                dynamic_data=dynamic_data
            )
            
            if not signal_data:
                return
            
            can_send, reason = risk_manager.can_send_signal(symbol, signal_data['priority'])
            
            if not can_send:
                logger.warning(f"⛔ [Main] Signal rejected for {symbol}: {reason}")
                return
            
            message_id = await telegram_dispatcher.send_signal(signal_data)
            
            with db_manager.get_session() as session:
                from bot.database.models import Signal as SignalModel
                from decimal import Decimal
                
                signal_obj = SignalModel(
                    id=signal_data['signal_id'],
                    symbol=signal_data['symbol'],
                    direction=signal_data['direction'],
                    signal_type=signal_data['signal_type'],
                    priority=signal_data['priority'],
                    entry_price=Decimal(str(signal_data['entry_price'])),
                    stop_loss=Decimal(str(signal_data['stop_loss'])),
                    take_profit_1=Decimal(str(signal_data['take_profit_1'])),
                    take_profit_2=Decimal(str(signal_data['take_profit_2'])),
                    quality_score=signal_data['quality_score'],
                    orderbook_imbalance=signal_data['orderbook_imbalance'],
                    large_trades_count=signal_data['large_trades_count'],
                    volume_intensity=signal_data['volume_intensity'],
                    confidence=signal_data['confidence'],
                    suggested_position_size=signal_data['suggested_position_size'],
                    risk_reward_ratio=signal_data['risk_reward_ratio'],
                    expected_hold_time=signal_data['expected_hold_time'],
                    telegram_message_id=message_id,
                    stop_loss_reason=signal_data.get('stop_loss_reason'),
                    tp1_reason=signal_data.get('tp1_reason'),
                    tp2_reason=signal_data.get('tp2_reason'),
                    support_level=Decimal(str(signal_data['support_level'])) if signal_data.get('support_level') else None,
                    resistance_level=Decimal(str(signal_data['resistance_level'])) if signal_data.get('resistance_level') else None,
                    status='OPEN'
                )
                session.add(signal_obj)
            
            logger.info(f"✅ [Main] Signal generated and saved: {symbol} {direction} @ ${price:.4f}")
            return True  # Signal generated successfully
            
        except Exception as e:
            logger.error(f"❌ [Main] Error generating signal for {symbol}: {e}")
            return False
    
    async def fast_signal_tracking_loop(self):
        """
        Fast signal tracking with 100ms hybrid exit strategy
        - Checks signals every 100ms from in-memory cache
        - Hybrid exit: imbalance normalized/reversed → SL/TP
        - Batch database operations for efficiency
        """
        logger.info("⚡ [Main] Starting 100ms fast signal tracking loop...")
        
        # Initial cache sync BEFORE first iteration
        await fast_signal_tracker.sync_cache_from_db()
        
        iteration = 0
        
        while self.running:
            try:
                # Sync cache from DB based on Config.CACHE_SYNC_INTERVAL
                sync_iterations = int(Config.CACHE_SYNC_INTERVAL / Config.FAST_TRACKING_INTERVAL)
                if iteration % sync_iterations == 0:
                    await fast_signal_tracker.sync_cache_from_db()
                
                # Check all open signals from cache
                exit_signals = []
                
                for signal_id, signal_data in list(fast_signal_tracker.open_signals_cache.items()):
                    try:
                        result = await fast_signal_tracker.check_signal_hybrid(signal_data)
                        if result:
                            exit_signals.append(result)
                    except Exception as e:
                        logger.error(f"❌ [FastTracking] Error checking signal {signal_id}: {e}")
                        continue
                
                # Batch close if any signals need to exit
                if exit_signals:
                    logger.info(f"⚡ [FastTracking] Found {len(exit_signals)} signals to close")
                    await fast_signal_tracker.close_signals_batch(exit_signals)
                    # Immediately refresh cache after closing
                    await fast_signal_tracker.sync_cache_from_db()
                
                iteration += 1
                
                # Wait based on Config.FAST_TRACKING_INTERVAL
                await asyncio.sleep(Config.FAST_TRACKING_INTERVAL)
                
            except Exception as e:
                logger.error(f"❌ [Main] Error in fast signal tracking loop: {e}")
                await asyncio.sleep(1)  # Pause on error
    
    async def metrics_update_loop(self):
        logger.info("📊 [Main] Starting metrics update loop...")
        
        while self.running:
            try:
                await asyncio.sleep(3600)
                
                metrics = performance_monitor.calculate_daily_metrics()
                if metrics:
                    performance_monitor.save_metrics(metrics)
                
            except Exception as e:
                logger.error(f"❌ [Main] Error in metrics update loop: {e}")
    
    async def shutdown(self):
        logger.info("🛑 [Main] Shutting down...")
        
        self.running = False
        
        await data_collector.stop_collecting()
        await telegram_bot_handler.stop_bot()
        await binance_client.close_async_session()
        await db_manager.close_async_pool()
        
        logger.info("✅ [Main] Shutdown complete")

async def main():
    bot = BinanceFuturesScanner()
    
    try:
        await bot.initialize()
        await bot.run()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Interrupted by user")
        sys.exit(0)
