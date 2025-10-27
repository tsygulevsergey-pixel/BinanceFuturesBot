#!/usr/bin/env python3
"""
Test script to verify Binance API and Telegram bot connectivity
Tests proxy, API keys, database, and Redis connections
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.utils.binance_client import binance_client
from bot.database import db_manager
from bot.modules.telegram_dispatcher import telegram_dispatcher

async def test_connections():
    logger.info("="*80)
    logger.info("🧪 Testing all connections...")
    logger.info("="*80)
    
    logger.info("\n1️⃣ Testing Redis connection...")
    try:
        redis_manager.connect()
        redis_manager.set('test_key', 'test_value', expiry=10)
        value = redis_manager.get('test_key')
        if value == 'test_value':
            logger.info("✅ Redis connection successful!")
        else:
            logger.error("❌ Redis connection failed - value mismatch")
            return False
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False
    
    logger.info("\n2️⃣ Testing PostgreSQL connection...")
    try:
        db_manager.init_sync_db()
        with db_manager.get_session() as session:
            result = session.execute("SELECT 1").fetchone()
            if result:
                logger.info("✅ PostgreSQL connection successful!")
            else:
                logger.error("❌ PostgreSQL connection failed")
                return False
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        return False
    
    logger.info("\n3️⃣ Testing Binance API connection (via proxy)...")
    try:
        binance_client.init_sync_client()
        await binance_client.init_async_session()
        
        server_time = await binance_client._make_request('GET', '/fapi/v1/time', weight=1)
        if server_time and 'serverTime' in server_time:
            logger.info(f"✅ Binance API connection successful! Server time: {server_time['serverTime']}")
        else:
            logger.error("❌ Binance API connection failed - no server time")
            return False
        
        exchange_info = await binance_client._make_request('GET', '/fapi/v1/exchangeInfo', weight=1)
        if exchange_info and 'symbols' in exchange_info:
            symbol_count = len(exchange_info['symbols'])
            logger.info(f"✅ Binance exchange info retrieved! Found {symbol_count} symbols")
        else:
            logger.error("❌ Failed to get exchange info")
            return False
            
    except Exception as e:
        logger.error(f"❌ Binance API connection failed: {e}")
        return False
    
    logger.info("\n4️⃣ Testing Telegram bot connection...")
    try:
        await telegram_dispatcher.initialize()
        
        test_message = await telegram_dispatcher.send_notification("🧪 **Connection Test**\n\n✅ Bot initialized successfully!")
        
        if test_message:
            logger.info("✅ Telegram bot connection successful!")
        else:
            logger.error("❌ Telegram bot connection failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Telegram bot connection failed: {e}")
        return False
    
    logger.info("\n5️⃣ Testing Binance ticker (sample data)...")
    try:
        ticker = await binance_client._make_request('GET', '/fapi/v1/ticker/price', params={'symbol': 'BTCUSDT'}, weight=1)
        if ticker and 'price' in ticker:
            logger.info(f"✅ Sample ticker data: BTCUSDT @ ${float(ticker['price']):,.2f}")
        else:
            logger.error("❌ Failed to get ticker data")
            return False
    except Exception as e:
        logger.error(f"❌ Ticker test failed: {e}")
        return False
    
    logger.info("\n" + "="*80)
    logger.info("✅ ALL TESTS PASSED!")
    logger.info("="*80)
    
    await binance_client.close_async_session()
    
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_connections())
        sys.exit(0 if result else 1)
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        sys.exit(1)
