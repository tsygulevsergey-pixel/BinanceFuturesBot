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
    signal_generator,
    risk_manager,
    telegram_dispatcher,
    signal_tracker,
    performance_monitor
)
from bot.telegram_bot import telegram_bot_handler

class BinanceFuturesScanner:
    def __init__(self):
        self.running = False
        self.last_universe_scan = None
        
        logger.info("="*80)
        logger.info("🚀 Binance Futures Scanner Bot Initializing...")
        logger.info("="*80)
    
    async def initialize(self):
        try:
            logger.info("🔧 [Main] Starting initialization...")
            
            db_manager.init_sync_db()
            await db_manager.init_async_pool()
            
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
            
            # Start DataCollector for WebSocket data streaming
            active_symbols = universe_selector.get_active_symbols()
            if active_symbols:
                logger.info(f"🚀 [Main] Starting DataCollector for {len(active_symbols)} symbols...")
            
            tasks = [
                self.universe_scan_loop(),
                self.signal_generation_loop(),
                self.signal_tracking_loop(),
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
    
    async def universe_scan_loop(self):
        while self.running:
            try:
                await asyncio.sleep(Config.UNIVERSE_RESCAN_INTERVAL)
                
                logger.info("🔄 [Main] Rescanning universe...")
                
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
                    await asyncio.sleep(0.5)  # Small delay to avoid rate limits
                
                logger.info(f"✅ [Main] Completed signal check for {len(active_symbols)} symbols - Generated {signals_generated} signals")
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ [Main] Error in signal generation loop: {e}")
                await asyncio.sleep(60)
    
    async def check_and_generate_signal(self, symbol: str, active_symbols: list = []):
        try:
            orderbook = redis_manager.get(f'orderbook:{symbol}')
            if not orderbook:
                return
            
            trade_flow = redis_manager.get(f'trade_flow:{symbol}')
            if not trade_flow:
                return
            
            imbalance = orderbook_analyzer.calculate_imbalance(
                orderbook.get('bids', []),
                orderbook.get('asks', [])
            )
            
            # Calculate volume_intensity and add to trade_flow
            volume_per_minute = trade_flow.get('volume_per_minute', 0)
            volume_intensity = volume_per_minute / 1_000_000  # Convert to millions
            trade_flow['volume_intensity'] = volume_intensity  # Add to trade_flow!
            
            price = float(orderbook['bids'][0][0]) if orderbook.get('bids') else 0
            
            # VWAP temporarily disabled (checks set to True in signal_generator.py)
            # TODO: Implement real VWAP calculation from trade flow data
            # VWAP = Σ(price * volume) / Σ(volume)
            
            price_data = {
                'price': price,
                'vwap': price,  # Placeholder (not used in checks currently)
                'rsi': 50,
                'near_support': False,
                'near_resistance': False
            }
            
            orderbook_data = {
                'imbalance': imbalance
            }
            
            can_long, long_conditions = signal_generator.check_long_conditions(
                orderbook_data,
                trade_flow,
                price_data
            )
            
            can_short, short_conditions = signal_generator.check_short_conditions(
                orderbook_data,
                trade_flow,
                price_data
            )
            
            # Debug log for EVERY 10th symbol to see why signals aren't generated
            symbol_index = active_symbols.index(symbol) if symbol in active_symbols else -1
            if symbol_index % 10 == 0:  # Log every 10th symbol
                logger.info(f"📊 [DEBUG {symbol}] imb={imbalance:.3f}, large_buys={trade_flow.get('large_buys', 0)}, large_sells={trade_flow.get('large_sells', 0)}, vol_int={volume_intensity:.2f}")
                if not can_long and not can_short:
                    failed_long = [k for k, v in long_conditions.get('required', {}).items() if not v]
                    failed_short = [k for k, v in short_conditions.get('required', {}).items() if not v]
                    logger.info(f"📊 [DEBUG {symbol}] LONG failed: {failed_long}, SHORT failed: {failed_short}")
            
            direction = None
            if can_long:
                direction = 'LONG'
            elif can_short:
                direction = 'SHORT'
            
            if not direction:
                return
            
            signal_data = signal_generator.generate_signal(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                orderbook_data=orderbook_data,
                trade_flow=trade_flow,
                price_data=price_data
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
                    status='OPEN'
                )
                session.add(signal_obj)
            
            logger.info(f"✅ [Main] Signal generated and saved: {symbol} {direction} @ ${price:.4f}")
            return True  # Signal generated successfully
            
        except Exception as e:
            logger.error(f"❌ [Main] Error generating signal for {symbol}: {e}")
            return False
    
    async def signal_tracking_loop(self):
        logger.info("👁️ [Main] Starting signal tracking loop...")
        
        while self.running:
            try:
                await signal_tracker.check_signals()
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ [Main] Error in signal tracking loop: {e}")
                await asyncio.sleep(60)
    
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
