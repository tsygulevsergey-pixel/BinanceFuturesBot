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
            
            if not self.database_url:
                raise ValueError("DATABASE_URL is not set")
            
            # Use smaller pool to avoid connection exhaustion
            self.engine = create_engine(
                self.database_url,
                pool_size=5,          # Reduced from 20
                max_overflow=10,      # Reduced from 40
                pool_pre_ping=True,
                pool_recycle=3600,    # Recycle connections every hour
                echo=False,
                connect_args={"connect_timeout": 10}  # 10 second timeout
            )
            
            self.session_factory = scoped_session(sessionmaker(bind=self.engine))
            
            # Create all tables if they don't exist
            Base.metadata.create_all(self.engine)
            logger.info("✅ [DatabaseManager] Database connection ready, all tables created/verified")
            
        except Exception as e:
            logger.error(f"❌ [DatabaseManager] Failed to initialize database: {e}", exc_info=True)
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
            
            if not self.database_url:
                raise ValueError("DATABASE_URL is not set")
            
            # Use smaller pool to avoid connection exhaustion and timeout issues
            self.async_pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,           # Reduced from 10
                max_size=10,          # Reduced from 50
                command_timeout=30,   # Reduced from 60
                timeout=10            # Connection timeout 10s
            )
            logger.info("✅ [DatabaseManager] Async database pool created successfully (2-10 connections)")
        except Exception as e:
            logger.error(f"❌ [DatabaseManager] Failed to create async pool: {e}", exc_info=True)
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
