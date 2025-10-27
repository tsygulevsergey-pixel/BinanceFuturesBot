#!/usr/bin/env python3
"""
Simple test for Binance API and Telegram bot connectivity
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from bot.config import Config
from bot.utils import logger
from bot.utils.binance_client import binance_client
from bot.modules.telegram_dispatcher import telegram_dispatcher

async def test_binance_and_telegram():
    logger.info("="*80)
    logger.info("🧪 Testing Binance API and Telegram Bot...")
    logger.info("="*80)
    
    logger.info("\n1️⃣ Testing Binance API connection via proxy...")
    try:
        binance_client.init_sync_client()
        await binance_client.init_async_session()
        
        server_time = await binance_client._make_request('GET', '/fapi/v1/time', weight=1)
        if server_time and 'serverTime' in server_time:
            logger.info(f"✅ Binance API connected! Server time: {server_time['serverTime']}")
        else:
            logger.error("❌ Binance API failed - no server time")
            return False
        
        ticker = await binance_client._make_request('GET', '/fapi/v1/ticker/price', params={'symbol': 'BTCUSDT'}, weight=1)
        if ticker and 'price' in ticker:
            logger.info(f"✅ BTC/USDT price: ${float(ticker['price']):,.2f}")
        else:
            logger.error("❌ Failed to get ticker")
            return False
            
    except Exception as e:
        logger.error(f"❌ Binance API test failed: {e}")
        return False
    
    logger.info("\n2️⃣ Testing Telegram bot...")
    try:
        await telegram_dispatcher.initialize()
        
        test_msg = await telegram_dispatcher.send_notification(
            "🧪 **Connection Test Successful!**\n\n✅ Binance API connected\n✅ Telegram bot connected\n\n🚀 Bot is ready to start!"
        )
        
        if test_msg:
            logger.info("✅ Telegram bot connected and test message sent!")
        else:
            logger.error("❌ Telegram failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Telegram test failed: {e}")
        return False
    
    logger.info("\n" + "="*80)
    logger.info("✅ ALL TESTS PASSED! Bot is ready to run.")
    logger.info("="*80)
    
    await binance_client.close_async_session()
    
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_binance_and_telegram())
        sys.exit(0 if result else 1)
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        sys.exit(1)
