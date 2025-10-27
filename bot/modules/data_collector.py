"""
Data Collector - collects real-time data via WebSocket
Streams: orderbook depth, aggregate trades, klines
Updates Redis cache and triggers analysis
"""
import asyncio
import json
import websockets
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
        
        logger.info("🔧 [DataCollector] Initialized")
    
    async def start_collecting(self, symbols: List[str]):
        try:
            self.active_symbols = symbols
            self.running = True
            
            logger.info(f"🚀 [DataCollector] Starting data collection for {len(symbols)} symbols...")
            
            tasks = []
            for symbol in symbols[:20]:
                tasks.append(self.collect_symbol_data(symbol))
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"❌ [DataCollector] Error in data collection: {e}")
    
    async def collect_symbol_data(self, symbol: str):
        symbol_lower = symbol.lower()
        
        streams = [
            f"{symbol_lower}@depth@100ms",
            f"{symbol_lower}@aggTrade",
            f"{symbol_lower}@kline_15m"
        ]
        
        stream_url = f"{self.base_url}/stream?streams={'/'.join(streams)}"
        
        while self.running:
            try:
                logger.debug(f"📡 [DataCollector] Connecting to WebSocket for {symbol}...")
                
                async with websockets.connect(stream_url) as ws:
                    logger.info(f"✅ [DataCollector] Connected to WebSocket for {symbol}")
                    
                    async for message in ws:
                        if not self.running:
                            break
                        
                        await self.process_message(symbol, message)
                        
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"⚠️ [DataCollector] WebSocket connection closed for {symbol}, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"❌ [DataCollector] WebSocket error for {symbol}: {e}")
                await asyncio.sleep(5)
    
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
