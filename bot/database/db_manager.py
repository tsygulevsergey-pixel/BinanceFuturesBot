"""
Database manager for PostgreSQL operations
Handles all database interactions with proper error handling and logging
"""
import asyncpg
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
from bot.config import Config
from bot.utils import logger
from bot.database.models import Base, Symbol, Signal, Trade, PerformanceMetrics, DailyStats

class DatabaseManager:
    def __init__(self):
        self.database_url = Config.DATABASE_URL
        self.engine = None
        self.session_factory = None
        self.async_pool = None
        
    def init_sync_db(self):
        try:
            logger.info("🔧 [DatabaseManager] Initializing synchronous database connection...")
            self.engine = create_engine(
                self.database_url,
                pool_size=20,
                max_overflow=40,
                pool_pre_ping=True,
                echo=False
            )
            
            self.session_factory = scoped_session(sessionmaker(bind=self.engine))
            
            logger.info("📝 [DatabaseManager] Creating database tables...")
            Base.metadata.create_all(self.engine)
            logger.info("✅ [DatabaseManager] Database tables created successfully")
            
        except Exception as e:
            logger.error(f"❌ [DatabaseManager] Failed to initialize database: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"❌ [DatabaseManager] Session error: {e}")
            raise
        finally:
            session.close()
    
    async def init_async_pool(self):
        try:
            logger.info("🔧 [DatabaseManager] Initializing async database connection pool...")
            self.async_pool = await asyncpg.create_pool(
                self.database_url,
                min_size=10,
                max_size=50,
                command_timeout=60
            )
            logger.info("✅ [DatabaseManager] Async database pool created successfully")
        except Exception as e:
            logger.error(f"❌ [DatabaseManager] Failed to create async pool: {e}")
            raise
    
    async def close_async_pool(self):
        if self.async_pool:
            await self.async_pool.close()
            logger.info("🔒 [DatabaseManager] Async database pool closed")
    
    async def execute_async(self, query, *args):
        try:
            async with self.async_pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"❌ [DatabaseManager] Async query error: {e}")
            raise

db_manager = DatabaseManager()
