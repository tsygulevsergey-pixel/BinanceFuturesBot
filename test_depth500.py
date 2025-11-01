#!/usr/bin/env python3
"""
Unit test для проверки depth=500 запросов в check_long_conditions
"""
import asyncio
import sys
sys.path.insert(0, '/home/runner/workspace')

from bot.modules.signal_generator import SignalGenerator
from bot.utils.binance_client import binance_client
from bot.database.db_manager import db_manager
from bot.modules.orderbook_analyzer import orderbook_analyzer

async def test_depth500():
    """Test depth=500 fetch in check_long_conditions"""
    print("=" * 80)
    print("🧪 Testing depth=500 fetch in SignalGenerator")
    print("=" * 80)
    
    # Initialize signal generator
    await db_manager.init_async_pool()
    signal_gen = SignalGenerator(db_manager.async_pool)
    
    print("\n✅ SignalGenerator initialized")
    
    # Create mock data (these will be ignored, depth=500 fetched internally)
    symbol = "BTCUSDT"
    orderbook_data = {}  # Empty (will fetch depth=500 internally)
    trade_flow = {
        'large_buys': 5,  # Pass basic condition
        'volume_per_minute': 5000000,
        'volume_intensity': 3.0  # Pass basic condition
    }
    price_data = {
        'price': 109800.0,
        'vwap': 109700.0,  # price > vwap (LONG condition)
        'rsi': 50
    }
    
    print(f"\n📊 Testing {symbol} with MOCK trade_flow and price_data")
    print(f"   - Mock large_buys: {trade_flow['large_buys']}")
    print(f"   - Mock volume_intensity: {trade_flow['volume_intensity']}")
    print(f"   - Mock price: ${price_data['price']}, vwap: ${price_data['vwap']}")
    
    print("\n🔍 Calling check_long_conditions() - should fetch depth=500 internally...")
    
    try:
        can_long, long_conditions = await signal_gen.check_long_conditions(
            symbol=symbol,
            orderbook_data=orderbook_data,
            trade_flow=trade_flow,
            price_data=price_data
        )
        
        print(f"\n📊 Results:")
        print(f"   - can_long: {can_long}")
        if long_conditions:
            print(f"   - global_imbalance: {long_conditions.get('global_imbalance', 'N/A')}")
            print(f"   - required conditions: {long_conditions.get('required', {})}")
            if 'stop_loss' in long_conditions:
                print(f"   - stop_loss: ${long_conditions['stop_loss'].get('stop_loss_price', 'N/A')}")
            if 'take_profit' in long_conditions:
                tp_info = long_conditions['take_profit']
                print(f"   - TP1: ${tp_info.get('tp1_price', 'N/A')} ({tp_info.get('tp1_distance_pct', 0):.2f}%)")
                print(f"   - TP2: ${tp_info.get('tp2_price', 'N/A')} ({tp_info.get('tp2_distance_pct', 0):.2f}%)")
            if 'validation' in long_conditions:
                val = long_conditions['validation']
                print(f"   - validation: {'PASSED' if val.get('is_valid') else 'FAILED'}")
                print(f"   - priority: {val.get('priority')}")
                if not val.get('is_valid'):
                    print(f"   - rejection_reasons: {val.get('rejection_reasons', [])}")
        
        print("\n✅ depth=500 fetch test PASSED!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await db_manager.close_async_pool()
        await binance_client.session.close()

if __name__ == '__main__':
    asyncio.run(test_depth500())
