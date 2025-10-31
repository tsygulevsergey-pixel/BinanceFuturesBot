#!/usr/bin/env python3
"""
Clear all signals and statistics from database
USE WITH CAUTION - This will delete ALL trading history!
"""
import asyncio
import sys
from bot.database import db_manager
from bot.utils import logger

async def clear_all_stats():
    """Clear all tables with confirmation"""
    
    print("\n" + "="*80)
    print("⚠️  WARNING: This will DELETE ALL trading data!")
    print("="*80)
    print("Tables to be cleared:")
    print("  - signals (all open/closed signals)")
    print("  - trades (all closed trades)")
    print("  - performance_metrics (daily stats)")
    print("="*80)
    
    confirmation = input("\nType 'DELETE ALL' to confirm: ")
    
    if confirmation != "DELETE ALL":
        print("❌ Cancelled. No data was deleted.")
        return
    
    print("\n🗑️  Clearing database...")
    
    try:
        with db_manager.get_session() as session:
            # Clear trades
            result = session.execute("DELETE FROM trades")
            trades_deleted = result.rowcount
            logger.info(f"✅ Deleted {trades_deleted} trades")
            
            # Clear signals
            result = session.execute("DELETE FROM signals")
            signals_deleted = result.rowcount
            logger.info(f"✅ Deleted {signals_deleted} signals")
            
            # Clear performance metrics
            result = session.execute("DELETE FROM performance_metrics")
            metrics_deleted = result.rowcount
            logger.info(f"✅ Deleted {metrics_deleted} performance metrics")
            
            session.commit()
            
            print("\n" + "="*80)
            print("✅ DATABASE CLEARED!")
            print("="*80)
            print(f"Deleted:")
            print(f"  - {signals_deleted} signals")
            print(f"  - {trades_deleted} trades")
            print(f"  - {metrics_deleted} performance metrics")
            print("="*80)
            print("\n🎯 Statistics reset to 0. Ready for testing!")
            
    except Exception as e:
        logger.error(f"❌ Error clearing database: {e}")
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(clear_all_stats())
