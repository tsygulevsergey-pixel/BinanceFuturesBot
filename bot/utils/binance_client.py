"""
Binance Futures API client with proxy support
All requests go through proxy: 23.27.184.165:5766:fyplvqgw:04azcek13s9n
Integrates with rate limiter for automatic request control
"""
import aiohttp
import hmac
import hashlib
import time
from typing import Dict, Optional, Any
from urllib.parse import urlencode
from binance.client import Client
from binance.exceptions import BinanceAPIException
from bot.config import Config
from bot.utils import logger
from bot.utils.rate_limiter import rate_limiter

class BinanceProxyClient:
    BASE_URL = 'https://fapi.binance.com'
    
    def __init__(self):
        self.api_key = Config.BINANCE_API_KEY
        self.api_secret = Config.BINANCE_API_SECRET
        self.proxy = Config.PROXY_URL
        
        self.sync_client = None
        self.session = None
        
        logger.info(f"🔧 [BinanceClient] Initializing with proxy: {self.proxy}")
    
    def init_sync_client(self):
        try:
            logger.info("🔧 [BinanceClient] Initializing synchronous client with proxy...")
            
            self.sync_client = Client(
                api_key=self.api_key,
                api_secret=self.api_secret,
                requests_params={
                    'proxies': Config.PROXY,
                    'timeout': 30  # 30 seconds timeout for proxy connections
                }
            )
            
            info = self.sync_client.futures_exchange_info()
            logger.info(f"✅ [BinanceClient] Connected to Binance Futures API, {len(info['symbols'])} symbols available")
            
        except Exception as e:
            logger.error(f"❌ [BinanceClient] Failed to initialize sync client: {e}")
            raise
    
    async def init_async_session(self):
        try:
            logger.info("🔧 [BinanceClient] Initializing async session with proxy...")
            
            # Configure connector for stable connection pooling with proxy
            connector = aiohttp.TCPConnector(
                ssl=False,
                limit=50,              # Max total connections
                limit_per_host=10,     # Max connections per host (Binance API)
                force_close=True,      # Force close connections after use (critical for proxy stability)
                enable_cleanup_closed=True  # Clean up closed connections
            )
            timeout = aiohttp.ClientTimeout(total=30)
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            
            logger.info("✅ [BinanceClient] Async session initialized with optimized connector (limit=50, force_close=True)")
            
        except Exception as e:
            logger.error(f"❌ [BinanceClient] Failed to initialize async session: {e}")
            raise
    
    async def close_async_session(self):
        if self.session:
            await self.session.close()
            logger.info("🔒 [BinanceClient] Async session closed")
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        signed: bool = False,
        weight: Optional[int] = None
    ) -> Any:
        if params is None:
            params = {}
        
        while not rate_limiter.add_request(endpoint, weight):
            rate_limiter.wait_if_needed()
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
        
        url = f"{self.BASE_URL}{endpoint}"
        headers = {'X-MBX-APIKEY': self.api_key} if signed else {}
        
        try:
            logger.debug(f"📡 [BinanceClient] {method} {endpoint} params={params}")
            
            if method == 'GET':
                async with self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    proxy=self.proxy
                ) as response:
                    rate_limiter.correct_from_headers(dict(response.headers))
                    
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"❌ [BinanceClient] Request failed: {response.status} - {text}")
                        return None
                    
                    data = await response.json()
                    logger.debug(f"✅ [BinanceClient] Request successful")
                    return data
                    
        except Exception as e:
            logger.error(f"❌ [BinanceClient] Request error for {endpoint}: {e}")
            return None
    
    async def get_exchange_info(self) -> Optional[Dict]:
        logger.info("📝 [BinanceClient] Fetching exchange info...")
        return await self._make_request('GET', '/fapi/v1/exchangeInfo', weight=1)
    
    async def get_24hr_tickers(self) -> Optional[list]:
        logger.info("📝 [BinanceClient] Fetching 24hr tickers...")
        return await self._make_request('GET', '/fapi/v1/ticker/24hr', weight=40)
    
    async def get_orderbook(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        logger.debug(f"📝 [BinanceClient] Fetching orderbook for {symbol}, limit={limit}")
        return await self._make_request(
            'GET',
            '/fapi/v1/depth',
            params={'symbol': symbol, 'limit': limit},
            weight=5 if limit <= 50 else 10
        )
    
    async def get_recent_trades(self, symbol: str, limit: int = 500) -> Optional[list]:
        logger.debug(f"📝 [BinanceClient] Fetching recent trades for {symbol}, limit={limit}")
        return await self._make_request(
            'GET',
            '/fapi/v1/aggTrades',
            params={'symbol': symbol, 'limit': limit},
            weight=20
        )
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[list]:
        logger.debug(f"📝 [BinanceClient] Fetching klines for {symbol}, interval={interval}, limit={limit}")
        return await self._make_request(
            'GET',
            '/fapi/v1/klines',
            params={'symbol': symbol, 'interval': interval, 'limit': limit},
            weight=5
        )
    
    async def get_open_interest(self, symbol: str) -> Optional[Dict]:
        logger.debug(f"📝 [BinanceClient] Fetching open interest for {symbol}")
        return await self._make_request(
            'GET',
            '/fapi/v1/openInterest',
            params={'symbol': symbol},
            weight=1
        )
    
    async def get_book_tickers(self) -> Optional[list]:
        """Get best bid/ask prices for all symbols (single batch request)"""
        logger.info("📝 [BinanceClient] Fetching book tickers (bid/ask prices) for all symbols...")
        return await self._make_request(
            'GET',
            '/fapi/v1/ticker/bookTicker',
            weight=5  # Weight for all symbols
        )
    
    async def get_orderbook_depth(self, symbol: str, limit: int = 500) -> Optional[Dict]:
        """
        Fetch deep orderbook from REST API for cluster analysis
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            limit: Number of levels (5, 10, 20, 50, 100, 500, 1000)
                   limit=500 → weight=10
        
        Returns:
            {
                'bids': [[price, qty], ...],  # 500 levels
                'asks': [[price, qty], ...]   # 500 levels
            }
        """
        logger.info(f"📊 [BinanceClient] Fetching deep orderbook for {symbol}, limit={limit}")
        
        # Weight calculation based on Binance API docs
        if limit <= 50:
            weight = 2
        elif limit <= 100:
            weight = 5
        elif limit <= 500:
            weight = 10
        elif limit <= 1000:
            weight = 20
        else:
            weight = 50
        
        return await self._make_request(
            'GET',
            '/fapi/v1/depth',
            params={'symbol': symbol, 'limit': limit},
            weight=weight
        )

binance_client = BinanceProxyClient()
