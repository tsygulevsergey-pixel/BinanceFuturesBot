#!/usr/bin/env python3
"""
Initialize database schema
Creates all necessary tables for the bot
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from bot.database import db_manager
from bot.utils import logger

def init_database():
    logger.info("="*80)
    logger.info("🗄️ Initializing database schema...")
    logger.info("="*80)
    
    try:
        db_manager.init_sync_db()
        
        logger.info("✅ Database schema initialized successfully!")
        logger.info("="*80)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
