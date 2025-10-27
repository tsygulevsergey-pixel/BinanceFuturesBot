"""
Dynamic universe selector - filters and scores trading pairs every 6 hours
Criteria: 24h volume >$50M, Open Interest >$10M, Spread <0.02%
Scoring: volume (35%), liquidity (25%), volatility (20%), activity (20%)
"""
import asyncio
from typing import List, Dict
from datetime import datetime, timedelta
from bot.config import Config
from bot.utils import logger
from bot.utils.binance_client import binance_client
from bot.utils.redis_manager import redis_manager
from bot.database import db_manager, Symbol
import numpy as np

class UniverseSelector:
    def __init__(self):
        self.weights = {
            'volume': 0.35,
            'liquidity': 0.25,
            'volatility': 0.20,
            'activity': 0.20
        }
        self.selected_symbols = []
        self.last_scan_time = None
        
        logger.info("🔧 [UniverseSelector] Initialized")
    
    async def scan_universe(self) -> List[str]:
        logger.info("🔍 [UniverseSelector] Starting universe scan...")
        start_time = datetime.now()
        
        try:
            exchange_info = await binance_client.get_exchange_info()
            if not exchange_info:
                logger.error("❌ [UniverseSelector] Failed to get exchange info")
                return self.selected_symbols
            
            usdt_symbols = [
                s['symbol'] for s in exchange_info['symbols']
                if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING'
            ]
            
            logger.info(f"📊 [UniverseSelector] Found {len(usdt_symbols)} USDT trading pairs")
            
            tickers = await binance_client.get_24hr_tickers()
            if not tickers:
                logger.error("❌ [UniverseSelector] Failed to get tickers")
                return self.selected_symbols
            
            ticker_dict = {t['symbol']: t for t in tickers if t['symbol'] in usdt_symbols}
            
            filtered_symbols = []
            for symbol in usdt_symbols:
                ticker = ticker_dict.get(symbol)
                if not ticker:
                    continue
                
                volume_24h = float(ticker.get('quoteVolume', 0))
                
                if volume_24h < Config.MIN_24H_VOLUME:
                    continue
                
                oi_data = await binance_client.get_open_interest(symbol)
                if not oi_data:
                    continue
                
                open_interest = float(oi_data.get('openInterest', 0))
                mark_price = float(oi_data.get('markPrice', 0))
                oi_value = open_interest * mark_price
                
                if oi_value < Config.MIN_OPEN_INTEREST:
                    continue
                
                bid_price = float(ticker.get('bidPrice', 0))
                ask_price = float(ticker.get('askPrice', 0))
                
                if bid_price > 0:
                    spread = (ask_price - bid_price) / bid_price
                    if spread > Config.MAX_SPREAD:
                        continue
                else:
                    spread = 0
                
                filtered_symbols.append({
                    'symbol': symbol,
                    'volume_24h': volume_24h,
                    'open_interest': oi_value,
                    'spread': spread,
                    'trades_24h': int(ticker.get('count', 0)),
                    'price_change_percent': float(ticker.get('priceChangePercent', 0))
                })
            
            logger.info(f"📊 [UniverseSelector] {len(filtered_symbols)} symbols passed initial filters")
            
            scored_symbols = []
            for symbol_data in filtered_symbols:
                score = await self.calculate_symbol_score(symbol_data)
                symbol_data['score'] = score
                scored_symbols.append(symbol_data)
            
            scored_symbols.sort(key=lambda x: x['score'], reverse=True)
            
            top_symbols = scored_symbols[:50]
            
            self.selected_symbols = [s['symbol'] for s in top_symbols]
            
            with db_manager.get_session() as session:
                session.query(Symbol).update({'is_active': False})
                
                for symbol_data in top_symbols:
                    symbol_obj = session.query(Symbol).filter_by(symbol=symbol_data['symbol']).first()
                    
                    if symbol_obj:
                        symbol_obj.score = symbol_data['score']
                        symbol_obj.volume_24h = symbol_data['volume_24h']
                        symbol_obj.open_interest = symbol_data['open_interest']
                        symbol_obj.spread = symbol_data['spread']
                        symbol_obj.trades_24h = symbol_data['trades_24h']
                        symbol_obj.is_active = True
                        symbol_obj.last_updated = datetime.now()
                    else:
                        symbol_obj = Symbol(
                            id=symbol_data['symbol'],
                            symbol=symbol_data['symbol'],
                            score=symbol_data['score'],
                            volume_24h=symbol_data['volume_24h'],
                            open_interest=symbol_data['open_interest'],
                            spread=symbol_data['spread'],
                            trades_24h=symbol_data['trades_24h'],
                            is_active=True
                        )
                        session.add(symbol_obj)
            
            redis_manager.set('active_symbols', self.selected_symbols, expiry=7200)
            
            self.last_scan_time = datetime.now()
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ [UniverseSelector] Universe scan completed in {elapsed:.2f}s, selected {len(self.selected_symbols)} symbols")
            top_symbols_str = ', '.join([f"{s['symbol']}({s['score']:.1f})" for s in top_symbols[:10]])
            logger.info(f"🏆 [UniverseSelector] Top 10 symbols by score: {top_symbols_str}")
            
            return self.selected_symbols
            
        except Exception as e:
            logger.error(f"❌ [UniverseSelector] Universe scan error: {e}")
            return self.selected_symbols
    
    async def calculate_symbol_score(self, symbol_data: Dict) -> float:
        try:
            score = 0
            
            volume_score = min(symbol_data['volume_24h'] / 100_000_000, 1)
            score += volume_score * self.weights['volume'] * 100
            
            liquidity_score = await self.calculate_liquidity_score(symbol_data['symbol'])
            score += liquidity_score * self.weights['liquidity'] * 100
            
            volatility_score = min(abs(symbol_data['price_change_percent']) / 10, 1)
            score += volatility_score * self.weights['volatility'] * 100
            
            activity_score = min(symbol_data['trades_24h'] / 86400 / 10, 1)
            score += activity_score * self.weights['activity'] * 100
            
            return score
            
        except Exception as e:
            logger.error(f"❌ [UniverseSelector] Error calculating score for {symbol_data.get('symbol')}: {e}")
            return 0
    
    async def calculate_liquidity_score(self, symbol: str) -> float:
        try:
            orderbook = await binance_client.get_orderbook(symbol, limit=20)
            if not orderbook:
                return 0
            
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                return 0
            
            mid_price = (float(bids[0][0]) + float(asks[0][0])) / 2
            depth_threshold = mid_price * 0.01
            
            bid_depth = sum(
                float(b[0]) * float(b[1])
                for b in bids
                if mid_price - float(b[0]) <= depth_threshold
            )
            
            ask_depth = sum(
                float(a[0]) * float(a[1])
                for a in asks
                if float(a[0]) - mid_price <= depth_threshold
            )
            
            total_depth = bid_depth + ask_depth
            
            liquidity_score = min(total_depth / 2_000_000, 1)
            
            return liquidity_score
            
        except Exception as e:
            logger.error(f"❌ [UniverseSelector] Error calculating liquidity for {symbol}: {e}")
            return 0
    
    def get_active_symbols(self) -> List[str]:
        cached = redis_manager.get('active_symbols')
        if cached:
            return cached
        return self.selected_symbols

universe_selector = UniverseSelector()
