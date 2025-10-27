"""
Redis manager for caching real-time data
Stores current market state, orderbook snapshots, trade flows
"""
import redis
import json
from typing import Any, Optional
from bot.config import Config
from bot.utils import logger

class RedisManager:
    def __init__(self):
        self.client = None
        self.fallback_cache = {}
        self.redis_available = False
        
    def connect(self):
        try:
            logger.info("🔧 [RedisManager] Connecting to Redis...")
            self.client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            self.client.ping()
            self.redis_available = True
            logger.info("✅ [RedisManager] Connected to Redis successfully")
        except Exception as e:
            logger.warning(f"⚠️ [RedisManager] Redis unavailable, using in-memory cache fallback: {e}")
            self.redis_available = False
            self.client = None
    
    def set(self, key: str, value: Any, expiry: Optional[int] = None):
        try:
            if self.redis_available and self.client:
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                else:
                    value_str = value
                
                if expiry:
                    self.client.setex(key, expiry, value_str)
                else:
                    self.client.set(key, value_str)
            else:
                self.fallback_cache[key] = value
                
            logger.debug(f"📝 [RedisManager] Set key: {key}")
        except Exception as e:
            logger.error(f"❌ [RedisManager] Error setting key {key}: {e}")
            self.fallback_cache[key] = value
    
    def get(self, key: str) -> Optional[Any]:
        try:
            if self.redis_available and self.client:
                value = self.client.get(key)
                if value:
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                return None
            else:
                return self.fallback_cache.get(key)
        except Exception as e:
            logger.error(f"❌ [RedisManager] Error getting key {key}: {e}")
            return self.fallback_cache.get(key)
    
    def delete(self, key: str):
        try:
            if self.redis_available and self.client:
                self.client.delete(key)
            else:
                self.fallback_cache.pop(key, None)
            logger.debug(f"🗑️ [RedisManager] Deleted key: {key}")
        except Exception as e:
            logger.error(f"❌ [RedisManager] Error deleting key {key}: {e}")
            self.fallback_cache.pop(key, None)
    
    def exists(self, key: str) -> bool:
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"❌ [RedisManager] Error checking key {key}: {e}")
            return False
    
    def incr(self, key: str, amount: int = 1) -> int:
        try:
            return self.client.incr(key, amount)
        except Exception as e:
            logger.error(f"❌ [RedisManager] Error incrementing key {key}: {e}")
            return 0
    
    def expire(self, key: str, seconds: int):
        try:
            self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"❌ [RedisManager] Error setting expiry for key {key}: {e}")
    
    def flushdb(self):
        try:
            self.client.flushdb()
            logger.info("🗑️ [RedisManager] Flushed Redis database")
        except Exception as e:
            logger.error(f"❌ [RedisManager] Error flushing database: {e}")

redis_manager = RedisManager()
