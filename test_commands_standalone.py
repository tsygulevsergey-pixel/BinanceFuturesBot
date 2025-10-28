"""
Standalone test for Telegram commands - starts ONLY the command handler
Tests /status and /stats commands without running full scanner bot
"""
import asyncio
from bot.config import Config
from bot.utils import logger
from bot.database import db_manager, Signal
from bot.utils.redis_manager import redis_manager
from bot.telegram_bot import telegram_bot_handler
from decimal import Decimal
from datetime import datetime, timedelta

async def setup_test_data():
    """Create test data for commands"""
    
    logger.info("📝 [TEST] Setting up test data...")
    
    # Initialize
    db_manager.init_sync_db()
    redis_manager.connect()
    
    # Create test signals
    test_signals = []
    
    # 3 profitable TP2 signals
    for i in range(3):
        signal_id = f"cmd_test_tp2_{i}_{int(datetime.now().timestamp())}"
        with db_manager.get_session() as session:
            signal = Signal(
                id=signal_id,
                symbol="BTCUSDT",
                direction="LONG",
                signal_type="MOMENTUM",
                priority="HIGH" if i == 0 else "MEDIUM",
                entry_price=Decimal("96000.00"),
                stop_loss=Decimal("94080.00"),
                take_profit_1=Decimal("97920.00"),
                take_profit_2=Decimal("98880.00"),
                quality_score=95,
                orderbook_imbalance=0.65,
                large_trades_count=5,
                volume_intensity=2.5,
                confidence=0.95,
                suggested_position_size=0.02,
                risk_reward_ratio=1.5,
                expected_hold_time="30-60 min",
                status="CLOSED",
                tp2_hit=True,
                tp2_hit_at=datetime.now() - timedelta(hours=1),
                closed_at=datetime.now() - timedelta(hours=1),
                close_price=Decimal("99000.00"),
                profit_loss_pct=3.125,
                created_at=datetime.now() - timedelta(hours=3)
            )
            session.add(signal)
            session.commit()
            test_signals.append(signal_id)
    
    # 1 TP1 signal
    signal_id = f"cmd_test_tp1_{int(datetime.now().timestamp())}"
    with db_manager.get_session() as session:
        signal = Signal(
            id=signal_id,
            symbol="ETHUSDT",
            direction="LONG",
            signal_type="MOMENTUM",
            priority="MEDIUM",
            entry_price=Decimal("3500.00"),
            stop_loss=Decimal("3430.00"),
            take_profit_1=Decimal("3570.00"),
            take_profit_2=Decimal("3605.00"),
            quality_score=88,
            orderbook_imbalance=0.45,
            large_trades_count=4,
            volume_intensity=2.2,
            confidence=0.88,
            suggested_position_size=0.02,
            risk_reward_ratio=1.5,
            expected_hold_time="30-60 min",
            status="CLOSED",
            tp1_hit=True,
            tp1_hit_at=datetime.now() - timedelta(minutes=30),
            closed_at=datetime.now() - timedelta(minutes=30),
            close_price=Decimal("3575.00"),
            profit_loss_pct=2.14,
            created_at=datetime.now() - timedelta(hours=2)
        )
        session.add(signal)
        session.commit()
        test_signals.append(signal_id)
    
    # 1 stop loss signal
    signal_id = f"cmd_test_sl_{int(datetime.now().timestamp())}"
    with db_manager.get_session() as session:
        signal = Signal(
            id=signal_id,
            symbol="SOLUSDT",
            direction="LONG",
            signal_type="MOMENTUM",
            priority="LOW",
            entry_price=Decimal("195.00"),
            stop_loss=Decimal("191.10"),
            take_profit_1=Decimal("198.90"),
            take_profit_2=Decimal("200.85"),
            quality_score=75,
            orderbook_imbalance=0.32,
            large_trades_count=3,
            volume_intensity=1.9,
            confidence=0.75,
            suggested_position_size=0.01,
            risk_reward_ratio=1.5,
            expected_hold_time="30-60 min",
            status="CLOSED",
            closed_at=datetime.now() - timedelta(minutes=10),
            close_price=Decimal("190.50"),
            profit_loss_pct=-2.31,
            created_at=datetime.now() - timedelta(hours=1)
        )
        session.add(signal)
        session.commit()
        test_signals.append(signal_id)
    
    # 2 open signals
    for i in range(2):
        signal_id = f"cmd_test_open_{i}_{int(datetime.now().timestamp())}"
        with db_manager.get_session() as session:
            signal = Signal(
                id=signal_id,
                symbol="BNBUSDT",
                direction="LONG",
                signal_type="MOMENTUM",
                priority="MEDIUM",
                entry_price=Decimal("620.00"),
                stop_loss=Decimal("607.60"),
                take_profit_1=Decimal("632.40"),
                take_profit_2=Decimal("638.60"),
                quality_score=85,
                orderbook_imbalance=0.55,
                large_trades_count=4,
                volume_intensity=2.3,
                confidence=0.85,
                suggested_position_size=0.02,
                risk_reward_ratio=1.5,
                expected_hold_time="30-60 min",
                status="OPEN",
                created_at=datetime.now() - timedelta(minutes=15)
            )
            session.add(signal)
            session.commit()
            test_signals.append(signal_id)
    
    # Set active symbols
    redis_manager.set('active_symbols', [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 
        'ADAUSDT', 'DOGEUSDT', 'XRPUSDT'
    ], expiry=3600)
    
    logger.info(f"✅ [TEST] Created {len(test_signals)} test signals:")
    logger.info(f"   - 3 TP2 signals (1 HIGH, 2 MEDIUM): +3.125% each")
    logger.info(f"   - 1 TP1 signal (MEDIUM): +2.14%")
    logger.info(f"   - 1 SL signal (LOW): -2.31%")
    logger.info(f"   - 2 OPEN signals (MEDIUM)")
    logger.info(f"✅ [TEST] Set 7 active symbols in Redis")
    logger.info("")
    
    return test_signals

async def cleanup_test_data(signal_ids):
    """Remove test data"""
    logger.info("")
    logger.info("🧹 [TEST] Cleaning up test data...")
    
    with db_manager.get_session() as session:
        for signal_id in signal_ids:
            signal = session.query(Signal).filter_by(id=signal_id).first()
            if signal:
                session.delete(signal)
        session.commit()
    
    logger.info("✅ [TEST] Test data cleaned up")

async def main():
    """Run standalone command test"""
    
    logger.info("")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 20 + "🤖 TELEGRAM COMMANDS TEST" + " " * 33 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    logger.info("")
    logger.info("This will start the Telegram command handler and keep it running")
    logger.info("so you can test /status and /stats commands")
    logger.info("")
    
    # Setup test data
    signal_ids = await setup_test_data()
    
    try:
        # Start telegram bot handler
        logger.info("=" * 80)
        logger.info("🚀 [TEST] Starting Telegram command handler...")
        logger.info("=" * 80)
        logger.info("")
        
        await telegram_bot_handler.start_bot()
        
        logger.info("✅ [TEST] Telegram bot handler is now RUNNING!")
        logger.info("")
        logger.info("=" * 80)
        logger.info("📱 NOW TEST THE COMMANDS IN TELEGRAM:")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Open your Telegram bot and send these commands:")
        logger.info("")
        logger.info("1️⃣  /status")
        logger.info("    Expected response:")
        logger.info("       📊 Bot Status")
        logger.info("       ✅ Status: Running 24/7")
        logger.info("       🔍 Analyzing: 7 symbols")
        logger.info("       📈 Open Signals: 2")
        logger.info("")
        logger.info("2️⃣  /stats")
        logger.info("    Expected response:")
        logger.info("       📊 Detailed Statistics (Today)")
        logger.info("       🎯 Signals Generated: 7")
        logger.info("       🔥 HIGH: 1")
        logger.info("       ⚡ MEDIUM: 5")
        logger.info("       💡 LOW: 1")
        logger.info("       ✅ Win Rate: 80.0%")
        logger.info("       💰 Total PnL: +7.08%")
        logger.info("       🎯 TP1 Hit: 1 times")
        logger.info("       🎯 TP2 Hit: 3 times")
        logger.info("       🛑 SL Hit: 1 times")
        logger.info("")
        logger.info("=" * 80)
        logger.info("")
        logger.info("⏰ Bot will run for 2 minutes... Test commands now!")
        logger.info("   Press Ctrl+C to stop earlier")
        logger.info("")
        
        # Keep running for 2 minutes
        for i in range(120, 0, -10):
            logger.info(f"   ⏳ {i} seconds remaining...")
            await asyncio.sleep(10)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ [TEST] Test time completed!")
        logger.info("=" * 80)
        
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⚠️ [TEST] Interrupted by user")
    except Exception as e:
        logger.error(f"❌ [TEST] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        logger.info("")
        logger.info("🛑 [TEST] Stopping bot handler...")
        await telegram_bot_handler.stop_bot()
        
        await cleanup_test_data(signal_ids)
        
        logger.info("")
        logger.info("✅ [TEST] Test completed and cleaned up!")
        logger.info("")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("")
        logger.info("👋 Bye!")
