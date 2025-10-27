#!/usr/bin/env python3
"""
Entry point for Binance Futures Scanner Bot
Runs the bot 24/7 with automatic reconnection on failures
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from bot.main import main
from bot.utils import logger

if __name__ == "__main__":
    logger.info("="*80)
    logger.info("🚀 Starting Binance Futures Scanner Bot...")
    logger.info("="*80)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
