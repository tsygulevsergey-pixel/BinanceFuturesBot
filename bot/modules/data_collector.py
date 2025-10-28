"""
Data Collector - collects real-time data via WebSocket
Streams: orderbook depth, aggregate trades, klines
Updates Redis cache and triggers analysis
"""
import asyncio
import json
import aiohttp
from typing import Dict, List, Set
from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.modules.orderbook_analyzer import orderbook_analyzer
from bot.modules.trade_flow_analyzer import trade_flow_analyzer

class DataCollector:
    def __init__(self):
        self.base_url = 'wss://fstream.binance.com'
        self.active_symbols = []
        self.websocket_connections = {}
        self.running = False
        self.proxy = Config.PROXY_URL  # Add proxy support
        
        logger.info("🔧 [DataCollector] Initialized")
    
    async def start_collecting(self, symbols: List[str]):
        try:
            self.active_symbols = symbols
            self.running = True
            
            logger.info(f"🚀 [DataCollector] Starting data collection for {len(symbols)} symbols...")
            logger.info(f"📊 [DataCollector] Total streams: {len(symbols) * 3} (limit: 1024)")
            
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
                f"{symbol_lower}@depth@100ms",
                f"{symbol_lower}@aggTrade",
                f"{symbol_lower}@kline_15m"
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
            
            if 'depth' in stream:
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
    
    async def process_depth(self, symbol: str, data: Dict):
        try:
            bids = data.get('b', [])
            asks = data.get('a', [])
            
            if not bids or not asks:
                return
            
            orderbook = {
                'bids': bids,
                'asks': asks,
                'timestamp': data.get('E', 0)
            }
            
            redis_manager.set(f'orderbook:{symbol}', orderbook, expiry=10)
            
            imbalance = orderbook_analyzer.calculate_imbalance(bids, asks)
            large_orders = orderbook_analyzer.detect_large_orders(orderbook)
            
            redis_manager.set(f'imbalance:{symbol}', imbalance, expiry=10)
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
            
            flow_analysis = trade_flow_analyzer.analyze_trade_flow(symbol)
            redis_manager.set(f'trade_flow:{symbol}', flow_analysis, expiry=60)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing trade for {symbol}: {e}")
    
    async def process_kline(self, symbol: str, data: Dict):
        try:
            kline = data.get('k', {})
            
            if not kline.get('x', False):
                return
            
            kline_data = {
                'open': float(kline.get('o', 0)),
                'high': float(kline.get('h', 0)),
                'low': float(kline.get('l', 0)),
                'close': float(kline.get('c', 0)),
                'volume': float(kline.get('v', 0)),
                'timestamp': kline.get('T', 0)
            }
            
            redis_manager.set(f'kline_15m:{symbol}', kline_data, expiry=900)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error processing kline for {symbol}: {e}")
    
    async def stop_collecting(self):
        self.running = False
        logger.info("🛑 [DataCollector] Stopping data collection...")

data_collector = DataCollector()
