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
            
            tasks = [
                self.universe_scan_loop(),
                self.signal_generation_loop(),
                self.signal_tracking_loop(),
                self.metrics_update_loop()
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
                
                for symbol in active_symbols[:10]:
                    await self.check_and_generate_signal(symbol)
                    await asyncio.sleep(1)
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ [Main] Error in signal generation loop: {e}")
                await asyncio.sleep(60)
    
    async def check_and_generate_signal(self, symbol: str):
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
            
            volume_intensity = trade_flow.get('volume_per_minute', 0) / 1_000_000
            
            price = float(orderbook['bids'][0][0]) if orderbook.get('bids') else 0
            
            price_data = {
                'price': price,
                'vwap': price,
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
            
        except Exception as e:
            logger.error(f"❌ [Main] Error generating signal for {symbol}: {e}")
    
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
