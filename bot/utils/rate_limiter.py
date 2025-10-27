"""
Internal rate limit calculator for Binance API
Tracks request weights and auto-corrects based on response headers
According to Binance Futures API limits: 2400 weight/minute default
"""
import time
from collections import deque
from typing import Dict, Optional
from bot.config import Config
from bot.utils import logger

class RateLimiter:
    ENDPOINT_WEIGHTS = {
        '/fapi/v1/exchangeInfo': 1,
        '/fapi/v1/ticker/24hr': 1,
        '/fapi/v1/ticker/price': 2,
        '/fapi/v1/depth': 5,
        '/fapi/v1/trades': 5,
        '/fapi/v1/aggTrades': 20,
        '/fapi/v1/klines': 5,
        '/fapi/v1/openInterest': 1,
        '/fapi/v1/fundingRate': 1,
        '/fapi/v1/premiumIndex': 10,
    }
    
    def __init__(self):
        self.max_weight = Config.BINANCE_RATE_LIMIT_WEIGHT
        self.window_seconds = 60
        
        self.requests = deque()
        self.current_weight = 0
        self.server_weight = None
        self.last_correction_time = time.time()
        
        logger.info(f"🔧 [RateLimiter] Initialized with max_weight={self.max_weight}/minute")
    
    def add_request(self, endpoint: str, weight: Optional[int] = None) -> bool:
        current_time = time.time()
        
        self._clean_old_requests(current_time)
        
        if weight is None:
            weight = self.ENDPOINT_WEIGHTS.get(endpoint, 1)
        
        if self.current_weight + weight > self.max_weight:
            logger.warning(f"⚠️ [RateLimiter] Rate limit approaching: {self.current_weight}/{self.max_weight}, waiting...")
            return False
        
        self.requests.append({
            'time': current_time,
            'weight': weight,
            'endpoint': endpoint
        })
        
        self.current_weight += weight
        
        logger.debug(f"📊 [RateLimiter] Added request: endpoint={endpoint}, weight={weight}, total={self.current_weight}/{self.max_weight}")
        
        return True
    
    def _clean_old_requests(self, current_time: float):
        cutoff_time = current_time - self.window_seconds
        
        while self.requests and self.requests[0]['time'] < cutoff_time:
            old_request = self.requests.popleft()
            self.current_weight -= old_request['weight']
        
        if self.current_weight < 0:
            self.current_weight = 0
    
    def correct_from_headers(self, headers: Dict[str, str]):
        try:
            if 'X-MBX-USED-WEIGHT-1M' in headers:
                server_weight = int(headers['X-MBX-USED-WEIGHT-1M'])
                
                if self.server_weight is not None:
                    diff = abs(server_weight - self.current_weight)
                    
                    if diff > 50:
                        logger.warning(
                            f"⚠️ [RateLimiter] Weight mismatch detected! Internal: {self.current_weight}, Server: {server_weight}, Diff: {diff}"
                        )
                        
                        self.current_weight = server_weight
                        logger.info(f"🔄 [RateLimiter] Corrected internal weight to server value: {server_weight}")
                    else:
                        logger.debug(f"✅ [RateLimiter] Weight verification: Internal={self.current_weight}, Server={server_weight}, Diff={diff}")
                
                self.server_weight = server_weight
                self.last_correction_time = time.time()
                
        except Exception as e:
            logger.error(f"❌ [RateLimiter] Error correcting from headers: {e}")
    
    def wait_if_needed(self) -> float:
        current_time = time.time()
        self._clean_old_requests(current_time)
        
        if self.current_weight >= self.max_weight * 0.9:
            if self.requests:
                oldest_request_time = self.requests[0]['time']
                wait_time = self.window_seconds - (current_time - oldest_request_time)
                
                if wait_time > 0:
                    logger.warning(f"⏸️ [RateLimiter] Rate limit reached ({self.current_weight}/{self.max_weight}), waiting {wait_time:.2f}s")
                    time.sleep(wait_time)
                    self._clean_old_requests(time.time())
                    return wait_time
        
        return 0.0
    
    def get_stats(self) -> Dict:
        current_time = time.time()
        self._clean_old_requests(current_time)
        
        return {
            'current_weight': self.current_weight,
            'max_weight': self.max_weight,
            'utilization': (self.current_weight / self.max_weight) * 100,
            'server_weight': self.server_weight,
            'requests_in_window': len(self.requests),
            'time_since_last_correction': current_time - self.last_correction_time
        }
    
    def reset(self):
        self.requests.clear()
        self.current_weight = 0
        logger.info("🔄 [RateLimiter] Rate limiter reset")

rate_limiter = RateLimiter()
