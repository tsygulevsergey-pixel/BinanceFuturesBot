"""
Quick standalone test for Telegram commands
Only tests /status command (simpler, no complex data needed)
"""
import asyncio
from bot.config import Config
from bot.utils import logger
from bot.database import db_manager, Signal, Trade
from bot.utils.redis_manager import redis_manager
from bot.telegram_bot import telegram_bot_handler
from decimal import Decimal
from datetime import datetime, timedelta

async def setup_simple_data():
    """Create minimal test data"""
    
    logger.info("📝 [TEST] Setting up simple test data...")
    
    # Initialize
    db_manager.init_sync_db()
    redis_manager.connect()
    
    # Create 2 open signals
    test_ids = []
    for i in range(2):
        signal_id = f"quick_test_{i}_{int(datetime.now().timestamp())}"
        with db_manager.get_session() as session:
            signal = Signal(
                id=signal_id,
                symbol="BTCUSDT",
                direction="LONG",
                signal_type="MOMENTUM",
                priority="HIGH",
                entry_price=Decimal("96500.00"),
                stop_loss=Decimal("94570.00"),
                take_profit_1=Decimal("98430.00"),
                take_profit_2=Decimal("99395.00"),
                quality_score=95,
                orderbook_imbalance=0.65,
                large_trades_count=5,
                volume_intensity=2.5,
                confidence=0.95,
                suggested_position_size=0.02,
                risk_reward_ratio=1.5,
                expected_hold_time="30-60 min",
                status="OPEN"
            )
            session.add(signal)
            session.commit()
            test_ids.append(signal_id)
    
    # Set active symbols
    redis_manager.set('active_symbols', [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT'
    ], expiry=3600)
    
    logger.info(f"✅ [TEST] Created 2 OPEN signals")
    logger.info(f"✅ [TEST] Set 5 active symbols")
    logger.info("")
    
    return test_ids

async def cleanup_data(signal_ids):
    """Remove test data"""
    logger.info("")
    logger.info("🧹 [TEST] Cleaning up...")
    
    with db_manager.get_session() as session:
        for signal_id in signal_ids:
            signal = session.query(Signal).filter_by(id=signal_id).first()
            if signal:
                session.delete(signal)
        session.commit()
    
    logger.info("✅ [TEST] Cleanup done")

async def main():
    """Run quick command test"""
    
    logger.info("")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 20 + "🤖 TELEGRAM COMMANDS TEST" + " " * 33 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    logger.info("")
    
    # Setup data
    signal_ids = await setup_simple_data()
    
    try:
        # Start bot handler
        logger.info("=" * 80)
        logger.info("🚀 [TEST] Starting Telegram command handler...")
        logger.info("=" * 80)
        logger.info("")
        
        await telegram_bot_handler.start_bot()
        
        logger.info("✅ [TEST] Telegram bot handler is RUNNING!")
        logger.info("")
        logger.info("=" * 80)
        logger.info("📱 TEST THESE COMMANDS IN TELEGRAM NOW:")
        logger.info("=" * 80)
        logger.info("")
        logger.info("1️⃣  /status")
        logger.info("    Expected:")
        logger.info("       ✅ Status: Running 24/7")
        logger.info("       🔍 Analyzing: 5 symbols")
        logger.info("       📈 Open Signals: 2")
        logger.info("")
        logger.info("2️⃣  /stats")
        logger.info("    Expected:")
        logger.info("       (Shows today's statistics)")
        logger.info("")
        logger.info("=" * 80)
        logger.info("")
        logger.info("⏰ Bot will run for 2 minutes... Test NOW!")
        logger.info("   Press Ctrl+C to stop earlier")
        logger.info("")
        
        # Keep running
        for i in range(120, 0, -10):
            logger.info(f"   ⏳ {i} seconds remaining...")
            await asyncio.sleep(10)
        
        logger.info("")
        logger.info("✅ [TEST] Time's up!")
        
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⚠️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("")
        logger.info("🛑 Stopping bot handler...")
        await telegram_bot_handler.stop_bot()
        
        await cleanup_data(signal_ids)
        
        logger.info("")
        logger.info("✅ Test completed!")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("")
        logger.info("👋 Bye!")
