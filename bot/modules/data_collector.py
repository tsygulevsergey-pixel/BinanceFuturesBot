"""
Data Collector - collects real-time data via WebSocket
Streams: orderbook depth, aggregate trades, klines (1m + 15m)
Updates Redis cache, saves 1m klines to PostgreSQL for ATR calculation
"""
import asyncio
import json
import aiohttp
from typing import Dict, List, Set
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.modules.orderbook_analyzer import orderbook_analyzer
from bot.modules.trade_flow_analyzer import trade_flow_analyzer
from bot.database import db_manager

class DataCollector:
    def __init__(self):
        self.base_url = 'wss://fstream.binance.com'
        self.active_symbols = []
        self.websocket_connections = {}
        self.running = False
        self.proxy = Config.PROXY_URL  # Add proxy support
        self.last_cleanup = datetime.now()
        self.cleanup_interval = 300  # Cleanup every 5 minutes
        
        logger.info("🔧 [DataCollector] Initialized")
    
    async def start_collecting(self, symbols: List[str]):
        try:
            self.active_symbols = symbols
            self.running = True
            
            logger.info(f"🚀 [DataCollector] Starting data collection for {len(symbols)} symbols...")
            logger.info(f"📊 [DataCollector] Total streams: {len(symbols) * 5} (bookTicker+depth20+aggTrade+kline_1m+kline_15m, limit: 1024)")
            
            # Backfill historical 1m klines for ATR calculation (so bot doesn't wait 15 minutes!)
            await self.backfill_historical_klines(symbols)
            
            # Use ONE combined WebSocket connection for ALL symbols (efficient!)
            await self.collect_all_symbols_combined(symbols)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error in data collection: {e}")
    
    async def collect_all_symbols_combined(self, symbols: List[str]):
        """Collect data for ALL symbols using ONE combined WebSocket connection with proxy"""
        
        # Build combined stream URL for all symbols
        all_streams = []
        for symbol in symbols:
            symbol_lower = symbol.lower()
            all_streams.extend([
                f"{symbol_lower}@bookTicker",  # Best bid/ask ONLY (accurate pricing!)
                # DISABLED: Switched to REST API depth=500 for global imbalance analysis
                # f"{symbol_lower}@depth20@100ms",  # Top 20 levels for orderbook analysis
                f"{symbol_lower}@aggTrade",
                f"{symbol_lower}@kline_1m",   # 1m klines for ATR calculation (saved to PostgreSQL)
                f"{symbol_lower}@kline_15m"   # 15m klines for volume analysis (saved to Redis)
            ])
        
        stream_url = f"{self.base_url}/stream?streams={'/'.join(all_streams)}"
        
        logger.info(f"📡 [DataCollector] Connecting to combined WebSocket for {len(symbols)} symbols with proxy...")
        
        message_count = 0
        last_heartbeat = asyncio.get_event_loop().time()
        
        while self.running:
            try:
                # Create aiohttp session with proxy support
                timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=300)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(stream_url, proxy=self.proxy, heartbeat=20) as ws:
                        logger.info(f"✅ [DataCollector] Connected! Streaming {len(all_streams)} streams for {len(symbols)} symbols")
                        
                        try:
                            async for msg in ws:
                                if not self.running:
                                    logger.info("🛑 [DataCollector] Stopping WebSocket (running=False)")
                                    break
                                
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    await self.process_combined_message(msg.data)
                                    message_count += 1
                                    
                                    # Heartbeat logging every 30 seconds
                                    current_time = asyncio.get_event_loop().time()
                                    if current_time - last_heartbeat >= 30:
                                        logger.info(f"💓 [DataCollector] WebSocket alive - {message_count} messages processed")
                                        last_heartbeat = current_time
                                    
                                    # Periodic cleanup of old klines data
                                    await self.cleanup_old_klines()
                                        
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    logger.error(f"❌ [DataCollector] WebSocket error: {ws.exception()}")
                                    break
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    logger.warning("⚠️ [DataCollector] WebSocket closed by server")
                                    break
                                    
                        except Exception as msg_error:
                            logger.error(f"❌ [DataCollector] Error in message loop: {msg_error}", exc_info=True)
                            break
                                
            except aiohttp.ClientError as e:
                logger.warning(f"⚠️ [DataCollector] WebSocket connection error, reconnecting in 5s... {e}")
                await asyncio.sleep(5)
            except asyncio.TimeoutError:
                logger.warning("⚠️ [DataCollector] WebSocket timeout, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"❌ [DataCollector] Combined WebSocket error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def process_combined_message(self, message: str):
        """Process messages from combined stream (includes symbol in stream name)"""
        try:
            data = json.loads(message)
            stream = data.get('stream', '')
            event_data = data.get('data', {})
            
            # Extract symbol from stream name (e.g., "btcusdt@depth@100ms" -> "BTCUSDT")
            symbol = stream.split('@')[0].upper()
            
            if 'bookTicker' in stream:
                await self.process_book_ticker(symbol, event_data)
            elif 'depth' in stream:
                await self.process_depth(symbol, event_data)
            elif 'aggTrade' in stream:
                await self.process_trade(symbol, event_data)
            elif 'kline' in stream:
                await self.process_kline(symbol, event_data)
                
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing combined message: {e}")
    
    async def process_message(self, symbol: str, message: str):
        try:
            data = json.loads(message)
            stream = data.get('stream', '')
            event_data = data.get('data', {})
            
            if 'depth' in stream:
                await self.process_depth(symbol, event_data)
            elif 'aggTrade' in stream:
                await self.process_trade(symbol, event_data)
            elif 'kline' in stream:
                await self.process_kline(symbol, event_data)
                
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing message for {symbol}: {e}")
    
    async def process_book_ticker(self, symbol: str, data: Dict):
        """Process bookTicker stream - provides best bid/ask prices in real-time"""
        try:
            best_bid = float(data.get('b', 0))  # Best bid price
            best_ask = float(data.get('a', 0))  # Best ask price
            
            if not best_bid or not best_ask:
                return
            
            # DIAGNOSTIC: Log prices from bookTicker for BTC, ETH, SOL (DEBUG level to avoid spam)
            if symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                logger.debug(f"📊 [BOOK TICKER] {symbol}: BID=${best_bid:,.2f}, ASK=${best_ask:,.2f}")
            
            # Store best prices in Redis for signal generation
            price_data = {
                'bid': best_bid,
                'ask': best_ask,
                'mid': (best_bid + best_ask) / 2,
                'timestamp': data.get('E', 0)
            }
            redis_manager.set(f'price:{symbol}', price_data, expiry=10)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing bookTicker for {symbol}: {e}")
    
    async def process_depth(self, symbol: str, data: Dict):
        """Process depth20 stream - provides top 20 bid/ask levels for orderbook analysis"""
        try:
            bids = data.get('bids', data.get('b', []))  # Support both formats
            asks = data.get('asks', data.get('a', []))
            
            if not bids or not asks:
                return
            
            # Store full orderbook for imbalance calculation
            orderbook = {
                'bids': bids,
                'asks': asks,
                'timestamp': data.get('E', 0)
            }
            
            redis_manager.set(f'orderbook:{symbol}', orderbook, expiry=10)
            
            # Calculate orderbook metrics
            imbalance = orderbook_analyzer.calculate_imbalance(bids, asks)
            large_orders = orderbook_analyzer.detect_large_orders(orderbook)
            
            # IMPORTANT: Store imbalance as dict (not float) for FastSignalTracker compatibility
            redis_manager.set(f'imbalance:{symbol}', {'imbalance': imbalance}, expiry=10)
            redis_manager.set(f'large_orders:{symbol}', large_orders, expiry=10)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing depth for {symbol}: {e}")
    
    async def process_trade(self, symbol: str, data: Dict):
        try:
            trade = {
                'T': data.get('T'),
                'p': data.get('p'),
                'q': data.get('q'),
                'm': data.get('m')
            }
            
            # DIAGNOSTIC: Log first 3 trades from Binance to verify data structure
            if not hasattr(self, '_trade_log_count'):
                self._trade_log_count = 0
            if self._trade_log_count < 3:
                price = float(trade.get('p', 0) or 0)
                qty = float(trade.get('q', 0) or 0)
                trade_size = price * qty
                is_sell = trade.get('m', False)
                logger.info(f"🔍 [DIAGNOSTIC] Trade #{self._trade_log_count + 1} from Binance: {symbol} - Price=${price:.2f}, Qty={qty:.4f}, Size=${trade_size:,.0f}, IsSell={is_sell}, Time={trade.get('T')}")
                self._trade_log_count += 1
            
            trade_flow_analyzer.add_trade(symbol, trade)
            
            # Run analyze_trade_flow in separate thread to avoid blocking event loop
            flow_analysis = await asyncio.to_thread(
                trade_flow_analyzer.analyze_trade_flow,
                symbol
            )
            redis_manager.set(f'trade_flow:{symbol}', flow_analysis, expiry=60)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing trade for {symbol}: {e}")
    
    async def process_kline(self, symbol: str, data: Dict):
        try:
            kline = data.get('k', {})
            interval = kline.get('i', '15m')  # Get interval (1m or 15m)
            
            kline_data = {
                'open': float(kline.get('o', 0)),
                'high': float(kline.get('h', 0)),
                'low': float(kline.get('l', 0)),
                'close': float(kline.get('c', 0)),
                'volume': float(kline.get('v', 0)),
                'timestamp': kline.get('T', 0),
                'is_closed': kline.get('x', False)
            }
            
            if interval == '1m':
                # 1m klines: Save ONLY closed candles to PostgreSQL for ATR calculation
                # This provides accurate True Range data for volatility analysis
                if kline.get('x', False):  # Only closed candles
                    await self.save_kline_to_db(symbol, interval, kline_data)
                    
                    # Log first closed 1m candle for diagnostics
                    if not hasattr(self, '_closed_1m_logged'):
                        self._closed_1m_logged = set()
                    if symbol not in self._closed_1m_logged:
                        logger.info(f"📊 [DataCollector] First 1m candle saved to DB for {symbol}")
                        self._closed_1m_logged.add(symbol)
                        
            elif interval == '15m':
                # 15m klines: Save ALL updates to Redis for volume_intensity calculation
                # Without this, bot waits up to 15 minutes for first closed candle!
                redis_manager.set(f'kline_15m:{symbol}', kline_data, expiry=900)
                
                # Log first closed 15m candle for diagnostics
                if kline.get('x', False):
                    if not hasattr(self, '_closed_15m_logged'):
                        self._closed_15m_logged = set()
                    if symbol not in self._closed_15m_logged:
                        logger.info(f"📊 [DataCollector] First 15m candle closed for {symbol}: vol={kline_data['volume']:,.0f}")
                        self._closed_15m_logged.add(symbol)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing kline for {symbol}: {e}")
    
    async def save_kline_to_db(self, symbol: str, interval: str, kline_data: Dict):
        """Save closed kline to PostgreSQL for ATR calculation"""
        try:
            if not db_manager.async_pool:
                logger.warning("⚠️ [DataCollector] Database pool not initialized, skipping kline save")
                return
                
            timestamp = datetime.fromtimestamp(kline_data['timestamp'] / 1000)
            
            query = """
                INSERT INTO klines (symbol, interval, timestamp, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol, interval, timestamp) DO NOTHING
            """
            
            async with db_manager.async_pool.acquire() as conn:
                await conn.execute(
                    query,
                    symbol,
                    interval,
                    timestamp,
                    kline_data['open'],
                    kline_data['high'],
                    kline_data['low'],
                    kline_data['close'],
                    kline_data['volume']
                )
                
            logger.debug(f"💾 [DataCollector] Saved {interval} kline for {symbol} to DB")
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error saving kline to DB for {symbol}: {e}")
    
    async def cleanup_old_klines(self):
        """Periodically cleanup klines older than 1 hour to save space"""
        try:
            now = datetime.now()
            if (now - self.last_cleanup).total_seconds() < self.cleanup_interval:
                return  # Not time yet
            
            if not db_manager.async_pool:
                return  # Pool not initialized yet
            
            self.last_cleanup = now
            cutoff_time = now - timedelta(hours=1)
            
            query = "DELETE FROM klines WHERE timestamp < $1"
            
            async with db_manager.async_pool.acquire() as conn:
                result = await conn.execute(query, cutoff_time)
                deleted_count = int(result.split()[-1]) if result else 0
                
                if deleted_count > 0:
                    logger.info(f"🧹 [DataCollector] Cleaned up {deleted_count} old klines (>1 hour)")
                    
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error cleaning up old klines: {e}")
    
    async def backfill_historical_klines(self, symbols: List[str]):
        """
        Load historical 1m klines from Binance REST API on startup
        This allows ATR calculation to work immediately without waiting 15 minutes!
        """
        try:
            if not db_manager.async_pool:
                logger.warning("⚠️ [DataCollector] Database pool not initialized, skipping backfill")
                return
            
            logger.info(f"📥 [DataCollector] Starting backfill of 1m klines for {len(symbols)} symbols...")
            
            # Check which symbols need backfill (missing data in last hour)
            symbols_to_backfill = await self.get_symbols_needing_backfill(symbols)
            
            if not symbols_to_backfill:
                logger.info(f"✅ [DataCollector] All symbols have recent 1m klines, skipping backfill")
                return
            
            logger.info(f"📥 [DataCollector] Backfilling {len(symbols_to_backfill)} symbols that need data...")
            
            # Fetch last 20 klines (1m) for each symbol via REST API
            import aiohttp
            url = "https://fapi.binance.com/fapi/v1/klines"
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                tasks = []
                for symbol in symbols_to_backfill:
                    tasks.append(self.fetch_and_save_klines(session, url, symbol))
                
                # Process in batches of 10 to avoid overwhelming API
                batch_size = 10
                for i in range(0, len(tasks), batch_size):
                    batch = tasks[i:i+batch_size]
                    await asyncio.gather(*batch, return_exceptions=True)
                    await asyncio.sleep(0.5)  # Rate limit protection
            
            logger.info(f"✅ [DataCollector] Backfill completed! ATR calculation ready immediately")
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error during backfill: {e}")
    
    async def get_symbols_needing_backfill(self, symbols: List[str]) -> List[str]:
        """Check which symbols have insufficient klines data in last hour"""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=20)
            
            query = """
                SELECT symbol, COUNT(*) as kline_count
                FROM klines
                WHERE interval = '1m'
                    AND timestamp >= $1
                GROUP BY symbol
            """
            
            async with db_manager.async_pool.acquire() as conn:
                rows = await conn.fetch(query, cutoff_time)
            
            existing_symbols = {row['symbol']: row['kline_count'] for row in rows}
            
            # Need backfill if: no data OR less than 15 klines
            symbols_needing_backfill = [
                s for s in symbols 
                if existing_symbols.get(s, 0) < 15
            ]
            
            return symbols_needing_backfill
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error checking backfill needs: {e}")
            return symbols  # Backfill all if check fails
    
    async def fetch_and_save_klines(self, session: aiohttp.ClientSession, url: str, symbol: str):
        """Fetch last 20 1m klines from Binance REST API and save to DB"""
        try:
            params = {
                'symbol': symbol,
                'interval': '1m',
                'limit': 20  # Get last 20 candles (enough for ATR14 + buffer)
            }
            
            async with session.get(url, params=params, proxy=self.proxy) as response:
                if response.status != 200:
                    logger.warning(f"⚠️ [DataCollector] Failed to fetch klines for {symbol}: HTTP {response.status}")
                    return
                
                klines = await response.json()
                
                # Save each kline to database
                saved_count = 0
                async with db_manager.async_pool.acquire() as conn:
                    for kline in klines:
                        timestamp = datetime.fromtimestamp(kline[0] / 1000)  # Open time
                        
                        query = """
                            INSERT INTO klines (symbol, interval, timestamp, open, high, low, close, volume)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (symbol, interval, timestamp) DO NOTHING
                        """
                        
                        await conn.execute(
                            query,
                            symbol,
                            '1m',
                            timestamp,
                            float(kline[1]),  # open
                            float(kline[2]),  # high
                            float(kline[3]),  # low
                            float(kline[4]),  # close
                            float(kline[5])   # volume
                        )
                        saved_count += 1
                
                logger.info(f"💾 [DataCollector] Backfilled {saved_count} 1m klines for {symbol}")
                
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error fetching klines for {symbol}: {e}")
    
    async def stop_collecting(self):
        self.running = False
        logger.info("🛑 [DataCollector] Stopping data collection...")

data_collector = DataCollector()
