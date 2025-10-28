"""
REAL Telegram test - sends actual messages to Telegram
Tests complete signal lifecycle with real Telegram notifications
"""
import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal

from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.database import db_manager, Signal as SignalModel
from bot.modules import (
    orderbook_analyzer,
    trade_flow_analyzer,
    signal_generator,
    telegram_dispatcher
)

async def generate_test_signal():
    """Generate a test signal with real market-like data"""
    symbol = "BTCUSDT"
    current_price = 96500.0
    
    logger.info("=" * 80)
    logger.info("🧪 [TELEGRAM TEST] Generating test signal for real Telegram notification")
    logger.info("=" * 80)
    
    # Simulate strong LONG conditions
    orderbook_data = {
        'imbalance': 0.65  # 65% buy pressure
    }
    
    trade_flow = {
        'large_buys': 8,
        'large_sells': 1,
        'volume_per_minute': 2_800_000,
        'volume_intensity': 2.8,
        'buy_sell_ratio': 3.5
    }
    
    price_data = {
        'price': current_price,
        'vwap': current_price * 0.998,  # Slightly below
        'rsi': 55,
        'near_support': False,
        'near_resistance': False
    }
    
    # Generate signal
    signal_data = signal_generator.generate_signal(
        symbol=symbol,
        direction='LONG',
        entry_price=current_price,
        orderbook_data=orderbook_data,
        trade_flow=trade_flow,
        price_data=price_data
    )
    
    logger.info(f"✅ [TEST] Signal generated:")
    logger.info(f"   - ID: {signal_data['signal_id']}")
    logger.info(f"   - Symbol: {signal_data['symbol']}")
    logger.info(f"   - Direction: {signal_data['direction']}")
    logger.info(f"   - Priority: {signal_data['priority']}")
    logger.info(f"   - Entry: ${signal_data['entry_price']:,.2f}")
    logger.info(f"   - TP1: ${signal_data['take_profit_1']:,.2f}")
    logger.info(f"   - TP2: ${signal_data['take_profit_2']:,.2f}")
    logger.info(f"   - SL: ${signal_data['stop_loss']:,.2f}")
    
    return signal_data

async def save_signal_to_db(signal_data):
    """Save signal to database"""
    logger.info("")
    logger.info("💾 [TEST] Saving signal to database...")
    
    with db_manager.get_session() as session:
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
            status='OPEN'
        )
        session.add(signal_obj)
        session.commit()
        
        logger.info(f"✅ [TEST] Signal saved to database")
        return signal_obj

async def send_signal_to_telegram(signal_data):
    """Send signal to Telegram (REAL MESSAGE!)"""
    logger.info("")
    logger.info("=" * 80)
    logger.info("📱 [TEST] Sending REAL signal to Telegram...")
    logger.info("=" * 80)
    
    # Initialize telegram bot
    await telegram_dispatcher.initialize()
    
    # Send signal
    message_id = await telegram_dispatcher.send_signal(signal_data)
    
    if message_id:
        logger.info(f"✅ [TEST] Signal sent to Telegram! Message ID: {message_id}")
        logger.info(f"📱 Check your Telegram app now!")
        return message_id
    else:
        logger.error("❌ [TEST] Failed to send signal to Telegram")
        return None

async def test_tp1_hit(signal_data, message_id):
    """Test TP1 hit scenario with Telegram notification"""
    logger.info("")
    logger.info("=" * 80)
    logger.info("🎯 [TEST] Simulating TP1 HIT...")
    logger.info("=" * 80)
    
    entry_price = signal_data['entry_price']
    tp1 = signal_data['take_profit_1']
    exit_price = tp1 + 20  # Slightly above TP1
    
    pnl_percent = ((exit_price - entry_price) / entry_price) * 100
    hold_time = 15  # 15 minutes
    
    logger.info(f"📊 Price reached ${exit_price:,.2f} (TP1: ${tp1:,.2f})")
    logger.info(f"💰 PnL: +{pnl_percent:.2f}%")
    logger.info("")
    logger.info("📱 Sending TP1 notification to Telegram...")
    
    # Update database
    with db_manager.get_session() as session:
        signal = session.query(SignalModel).filter_by(id=signal_data['signal_id']).first()
        if signal:
            signal.tp1_hit = True
            signal.tp1_hit_at = datetime.now()
            signal.telegram_message_id = message_id
            session.commit()
    
    # Send Telegram update
    success = await telegram_dispatcher.send_signal_update(
        signal_id=signal_data['signal_id'],
        symbol=signal_data['symbol'],
        exit_reason='TP1 HIT 🎯',
        entry_price=entry_price,
        exit_price=exit_price,
        pnl_percent=pnl_percent,
        hold_time_minutes=hold_time,
        original_message_id=message_id
    )
    
    if success:
        logger.info(f"✅ [TEST] TP1 notification sent to Telegram!")
        logger.info(f"📱 Check your Telegram for the update!")
    else:
        logger.error("❌ [TEST] Failed to send TP1 notification")
    
    # Wait a bit before next update
    await asyncio.sleep(3)

async def test_tp2_hit(signal_data, message_id):
    """Test TP2 hit scenario with Telegram notification"""
    logger.info("")
    logger.info("=" * 80)
    logger.info("🎯🎯 [TEST] Simulating TP2 HIT (FULL PROFIT)...")
    logger.info("=" * 80)
    
    entry_price = signal_data['entry_price']
    tp2 = signal_data['take_profit_2']
    exit_price = tp2 + 30  # Slightly above TP2
    
    pnl_percent = ((exit_price - entry_price) / entry_price) * 100
    hold_time = 45  # 45 minutes total
    
    logger.info(f"📊 Price reached ${exit_price:,.2f} (TP2: ${tp2:,.2f})")
    logger.info(f"💰 PnL: +{pnl_percent:.2f}%")
    logger.info("")
    logger.info("📱 Sending TP2 (CLOSED) notification to Telegram...")
    
    # Update database
    with db_manager.get_session() as session:
        signal = session.query(SignalModel).filter_by(id=signal_data['signal_id']).first()
        if signal:
            signal.tp2_hit = True
            signal.tp2_hit_at = datetime.now()
            signal.status = 'CLOSED'
            signal.closed_at = datetime.now()
            signal.close_price = Decimal(str(exit_price))
            signal.profit_loss_pct = pnl_percent
            session.commit()
    
    # Send Telegram update
    success = await telegram_dispatcher.send_signal_update(
        signal_id=signal_data['signal_id'],
        symbol=signal_data['symbol'],
        exit_reason='TP2 HIT 🎯🎯 (CLOSED)',
        entry_price=entry_price,
        exit_price=exit_price,
        pnl_percent=pnl_percent,
        hold_time_minutes=hold_time,
        original_message_id=message_id
    )
    
    if success:
        logger.info(f"✅ [TEST] TP2 (CLOSED) notification sent to Telegram!")
        logger.info(f"📱 Check your Telegram for the FINAL update!")
    else:
        logger.error("❌ [TEST] Failed to send TP2 notification")

async def test_stop_loss_scenario():
    """Test stop loss scenario with separate signal"""
    logger.info("")
    logger.info("=" * 80)
    logger.info("🛑 [TEST] Testing STOP LOSS scenario...")
    logger.info("=" * 80)
    
    # Generate new signal for SL test
    symbol = "ETHUSDT"
    entry_price = 3600.0
    
    sl_signal_data = signal_generator.generate_signal(
        symbol=symbol,
        direction='LONG',
        entry_price=entry_price,
        orderbook_data={'imbalance': 0.35},
        trade_flow={'large_buys': 4, 'large_sells': 1, 'volume_per_minute': 2_000_000, 'volume_intensity': 2.0, 'buy_sell_ratio': 2.5},
        price_data={'price': entry_price, 'vwap': entry_price * 0.999, 'rsi': 52}
    )
    
    # Save to DB
    with db_manager.get_session() as session:
        signal_obj = SignalModel(
            id=sl_signal_data['signal_id'],
            symbol=sl_signal_data['symbol'],
            direction=sl_signal_data['direction'],
            signal_type=sl_signal_data['signal_type'],
            priority=sl_signal_data['priority'],
            entry_price=Decimal(str(sl_signal_data['entry_price'])),
            stop_loss=Decimal(str(sl_signal_data['stop_loss'])),
            take_profit_1=Decimal(str(sl_signal_data['take_profit_1'])),
            take_profit_2=Decimal(str(sl_signal_data['take_profit_2'])),
            quality_score=sl_signal_data['quality_score'],
            orderbook_imbalance=sl_signal_data['orderbook_imbalance'],
            large_trades_count=sl_signal_data['large_trades_count'],
            volume_intensity=sl_signal_data['volume_intensity'],
            confidence=sl_signal_data['confidence'],
            suggested_position_size=sl_signal_data['suggested_position_size'],
            risk_reward_ratio=sl_signal_data['risk_reward_ratio'],
            expected_hold_time=sl_signal_data['expected_hold_time'],
            status='OPEN'
        )
        session.add(signal_obj)
        session.commit()
    
    # Send to Telegram
    logger.info("📱 Sending SL test signal to Telegram...")
    message_id = await telegram_dispatcher.send_signal(sl_signal_data)
    
    if not message_id:
        logger.error("❌ Failed to send SL signal")
        return
    
    logger.info(f"✅ SL signal sent! Message ID: {message_id}")
    
    # Wait a bit
    await asyncio.sleep(3)
    
    # Simulate stop loss hit
    stop_loss = sl_signal_data['stop_loss']
    exit_price = stop_loss - 10  # Below stop loss
    pnl_percent = ((exit_price - entry_price) / entry_price) * 100
    hold_time = 8  # 8 minutes
    
    logger.info("")
    logger.info(f"📉 Price dropped to ${exit_price:,.2f} (SL: ${stop_loss:,.2f})")
    logger.info(f"💰 PnL: {pnl_percent:.2f}%")
    logger.info("📱 Sending STOP LOSS notification to Telegram...")
    
    # Update database
    with db_manager.get_session() as session:
        signal = session.query(SignalModel).filter_by(id=sl_signal_data['signal_id']).first()
        if signal:
            signal.status = 'CLOSED'
            signal.closed_at = datetime.now()
            signal.close_price = Decimal(str(exit_price))
            signal.profit_loss_pct = pnl_percent
            signal.telegram_message_id = message_id
            session.commit()
    
    # Send Telegram update
    success = await telegram_dispatcher.send_signal_update(
        signal_id=sl_signal_data['signal_id'],
        symbol=sl_signal_data['symbol'],
        exit_reason='STOP LOSS HIT 🛑',
        entry_price=entry_price,
        exit_price=exit_price,
        pnl_percent=pnl_percent,
        hold_time_minutes=hold_time,
        original_message_id=message_id
    )
    
    if success:
        logger.info(f"✅ [TEST] STOP LOSS notification sent to Telegram!")
        logger.info(f"📱 Check your Telegram for the SL update!")
    else:
        logger.error("❌ [TEST] Failed to send SL notification")

async def main():
    """Run complete Telegram test"""
    try:
        logger.info("")
        logger.info("╔" + "=" * 78 + "╗")
        logger.info("║" + " " * 15 + "🚀 REAL TELEGRAM SIGNAL FLOW TEST" + " " * 30 + "║")
        logger.info("╚" + "=" * 78 + "╝")
        logger.info("")
        logger.info("This test will send REAL messages to your Telegram!")
        logger.info("")
        
        # Initialize database
        db_manager.init_sync_db()
        
        # Step 1: Generate test signal
        signal_data = await generate_test_signal()
        
        # Step 2: Save to database
        await save_signal_to_db(signal_data)
        
        # Step 3: Send to Telegram (REAL!)
        message_id = await send_signal_to_telegram(signal_data)
        
        if not message_id:
            logger.error("❌ Test failed - could not send to Telegram")
            return
        
        logger.info("")
        logger.info("⏳ Waiting 5 seconds before sending updates...")
        await asyncio.sleep(5)
        
        # Step 4: Test TP1 hit
        await test_tp1_hit(signal_data, message_id)
        
        logger.info("")
        logger.info("⏳ Waiting 5 seconds before TP2...")
        await asyncio.sleep(5)
        
        # Step 5: Test TP2 hit (full close)
        await test_tp2_hit(signal_data, message_id)
        
        logger.info("")
        logger.info("⏳ Waiting 5 seconds before SL test...")
        await asyncio.sleep(5)
        
        # Step 6: Test stop loss scenario
        await test_stop_loss_scenario()
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("🎉 [TEST] TELEGRAM TEST COMPLETED!")
        logger.info("=" * 80)
        logger.info("✅ Signal sent to Telegram")
        logger.info("✅ TP1 update sent")
        logger.info("✅ TP2 close sent")
        logger.info("✅ Stop Loss test sent")
        logger.info("")
        logger.info("📱 CHECK YOUR TELEGRAM NOW to see all messages!")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ [TEST] Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
