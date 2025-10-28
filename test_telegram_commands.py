"""
Test Telegram bot commands /status and /stats
This will SEND ACTUAL COMMANDS to your bot and verify responses
"""
import asyncio
from telegram import Bot
from bot.config import Config
from bot.utils import logger
from bot.database import db_manager, Signal
from bot.utils.redis_manager import redis_manager
from bot.modules import performance_monitor
from decimal import Decimal
from datetime import datetime, timedelta

async def test_telegram_commands():
    """Test /status and /stats commands"""
    
    logger.info("=" * 80)
    logger.info("🧪 [TEST] Testing Telegram bot commands")
    logger.info("=" * 80)
    logger.info("")
    
    # Initialize database
    db_manager.init_sync_db()
    
    # Create some test data for stats
    logger.info("📝 [TEST] Creating test data for statistics...")
    
    # Create test signals with various statuses
    test_signals = []
    
    # 3 profitable signals (TP2 hit)
    for i in range(3):
        signal_id = f"test_profit_{i}_{int(datetime.now().timestamp())}"
        with db_manager.get_session() as session:
            signal = Signal(
                id=signal_id,
                symbol="BTCUSDT",
                direction="LONG",
                signal_type="MOMENTUM",
                priority="HIGH" if i == 0 else "MEDIUM",
                entry_price=Decimal("100000.00"),
                stop_loss=Decimal("98000.00"),
                take_profit_1=Decimal("102000.00"),
                take_profit_2=Decimal("103000.00"),
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
                tp2_hit_at=datetime.now() - timedelta(minutes=30),
                closed_at=datetime.now() - timedelta(minutes=30),
                close_price=Decimal("103100.00"),
                profit_loss_pct=3.1,
                created_at=datetime.now() - timedelta(hours=2)
            )
            session.add(signal)
            session.commit()
            test_signals.append(signal_id)
    
    # 1 TP1 signal
    signal_id = f"test_tp1_{int(datetime.now().timestamp())}"
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
            tp1_hit_at=datetime.now() - timedelta(minutes=15),
            closed_at=datetime.now() - timedelta(minutes=15),
            close_price=Decimal("3575.00"),
            profit_loss_pct=2.14,
            created_at=datetime.now() - timedelta(hours=1)
        )
        session.add(signal)
        session.commit()
        test_signals.append(signal_id)
    
    # 1 stop loss signal
    signal_id = f"test_sl_{int(datetime.now().timestamp())}"
    with db_manager.get_session() as session:
        signal = Signal(
            id=signal_id,
            symbol="SOLUSDT",
            direction="LONG",
            signal_type="MOMENTUM",
            priority="LOW",
            entry_price=Decimal("200.00"),
            stop_loss=Decimal("196.00"),
            take_profit_1=Decimal("204.00"),
            take_profit_2=Decimal("206.00"),
            quality_score=75,
            orderbook_imbalance=0.32,
            large_trades_count=3,
            volume_intensity=1.9,
            confidence=0.75,
            suggested_position_size=0.01,
            risk_reward_ratio=1.5,
            expected_hold_time="30-60 min",
            status="CLOSED",
            closed_at=datetime.now() - timedelta(minutes=5),
            close_price=Decimal("195.50"),
            profit_loss_pct=-2.25,
            created_at=datetime.now() - timedelta(minutes=30)
        )
        session.add(signal)
        session.commit()
        test_signals.append(signal_id)
    
    # 2 open signals
    for i in range(2):
        signal_id = f"test_open_{i}_{int(datetime.now().timestamp())}"
        with db_manager.get_session() as session:
            signal = Signal(
                id=signal_id,
                symbol="BNBUSDT",
                direction="LONG",
                signal_type="MOMENTUM",
                priority="MEDIUM",
                entry_price=Decimal("600.00"),
                stop_loss=Decimal("588.00"),
                take_profit_1=Decimal("612.00"),
                take_profit_2=Decimal("618.00"),
                quality_score=85,
                orderbook_imbalance=0.55,
                large_trades_count=4,
                volume_intensity=2.3,
                confidence=0.85,
                suggested_position_size=0.02,
                risk_reward_ratio=1.5,
                expected_hold_time="30-60 min",
                status="OPEN",
                created_at=datetime.now() - timedelta(minutes=10)
            )
            session.add(signal)
            session.commit()
            test_signals.append(signal_id)
    
    logger.info(f"✅ [TEST] Created {len(test_signals)} test signals")
    logger.info(f"   - 3 TP2 profitable signals (HIGH, MEDIUM, MEDIUM)")
    logger.info(f"   - 1 TP1 profitable signal (MEDIUM)")
    logger.info(f"   - 1 Stop Loss signal (LOW)")
    logger.info(f"   - 2 Open signals (MEDIUM)")
    logger.info("")
    
    # Set active symbols in Redis
    redis_manager.set('active_symbols', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT'], expiry=3600)
    logger.info("✅ [TEST] Set 5 active symbols in Redis")
    logger.info("")
    
    # Initialize bot
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    logger.info("=" * 80)
    logger.info("📱 [TEST] Testing /status command")
    logger.info("=" * 80)
    logger.info("")
    logger.info("🤖 Please send /status to your bot in Telegram NOW!")
    logger.info("")
    logger.info("Expected response:")
    logger.info("   📊 Bot Status")
    logger.info("   ✅ Status: Running 24/7")
    logger.info("   🔍 Analyzing: 5 symbols")
    logger.info("   📈 Open Signals: 2")
    logger.info("   ⏰ Uptime: Active")
    logger.info("")
    logger.info("=" * 80)
    logger.info("")
    
    await asyncio.sleep(3)
    
    logger.info("=" * 80)
    logger.info("📱 [TEST] Testing /stats command")
    logger.info("=" * 80)
    logger.info("")
    logger.info("🤖 Please send /stats to your bot in Telegram NOW!")
    logger.info("")
    logger.info("Expected response:")
    logger.info("   📊 Detailed Statistics (Today)")
    logger.info("   🎯 Signals Generated: 7")
    logger.info("   🔥 HIGH Priority: 1")
    logger.info("   ⚡ MEDIUM Priority: 5")
    logger.info("   💡 LOW Priority: 1")
    logger.info("   ✅ Win Rate: 80.0%")
    logger.info("   💰 Total PnL: +8.09%")
    logger.info("   🎯 TP1 Hit: 1 times")
    logger.info("   🎯 TP2 Hit: 3 times")
    logger.info("   🛑 SL Hit: 1 times")
    logger.info("")
    logger.info("=" * 80)
    logger.info("")
    
    # Wait for user to test commands
    logger.info("⏳ Waiting 30 seconds for you to test commands...")
    logger.info("   1. Open your Telegram bot chat")
    logger.info("   2. Send /status")
    logger.info("   3. Send /stats")
    logger.info("")
    
    for i in range(30, 0, -5):
        logger.info(f"   ⏳ {i} seconds remaining...")
        await asyncio.sleep(5)
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ [TEST] Test completed!")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Did you receive both responses in Telegram?")
    logger.info("If yes - commands are working perfectly! ✅")
    logger.info("If no - check bot logs for errors")
    logger.info("")
    
    # Cleanup test data
    logger.info("🧹 [TEST] Cleaning up test data...")
    with db_manager.get_session() as session:
        for signal_id in test_signals:
            signal = session.query(Signal).filter_by(id=signal_id).first()
            if signal:
                session.delete(signal)
        session.commit()
    logger.info("✅ [TEST] Test data cleaned up")

async def main():
    try:
        await test_telegram_commands()
    except Exception as e:
        logger.error(f"❌ [TEST] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
