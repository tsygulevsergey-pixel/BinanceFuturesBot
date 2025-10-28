"""
Dynamic universe selector with 3-stage optimized filtering (reduces API calls)
Stage 1: 24h volume >$30M (in-memory filter, no API calls)
Stage 2: Open Interest >$5M (throttled concurrent API calls with semaphore)
Stage 3: Spread <0.02% or dynamic ATR-based (10% of ATR, using existing data)
Scoring: volume (35%), liquidity (25%), volatility (20%), activity (20%)
Rescans every 6 hours, selects top 50 symbols
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
    
    def _apply_blacklist(self, symbols: List[str]) -> List[str]:
        """Filter out blacklisted symbols and non-ASCII symbols"""
        filtered = []
        blacklisted_count = 0
        non_ascii_count = 0
        
        for symbol in symbols:
            # Check if in blacklist
            if symbol in Config.SYMBOL_BLACKLIST:
                blacklisted_count += 1
                continue
            
            # Check for non-ASCII characters (Chinese, Japanese, etc.)
            if Config.FILTER_NON_ASCII:
                try:
                    symbol.encode('ascii')
                except UnicodeEncodeError:
                    non_ascii_count += 1
                    logger.debug(f"🚫 [Blacklist] Filtered non-ASCII symbol: {symbol}")
                    continue
            
            filtered.append(symbol)
        
        if blacklisted_count > 0:
            logger.info(f"🚫 [Blacklist] Filtered {blacklisted_count} blacklisted symbols")
        if non_ascii_count > 0:
            logger.info(f"🚫 [Blacklist] Filtered {non_ascii_count} non-ASCII symbols")
        
        return filtered
    
    async def scan_universe(self) -> List[str]:
        logger.info("🔍 [UniverseSelector] Starting optimized 3-stage universe scan...")
        start_time = datetime.now()
        
        try:
            # Get exchange info and tickers (single API call)
            exchange_info = await binance_client.get_exchange_info()
            if not exchange_info:
                logger.error("❌ [UniverseSelector] Failed to get exchange info")
                return self.selected_symbols
            
            usdt_symbols = [
                s['symbol'] for s in exchange_info['symbols']
                if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING'
            ]
            logger.info(f"📊 [UniverseSelector] Found {len(usdt_symbols)} USDT trading pairs")
            
            # Apply blacklist filter
            usdt_symbols = self._apply_blacklist(usdt_symbols)
            logger.info(f"📊 [UniverseSelector] After blacklist filter: {len(usdt_symbols)} symbols")
            
            tickers = await binance_client.get_24hr_tickers()
            if not tickers:
                logger.error("❌ [UniverseSelector] Failed to get tickers")
                return self.selected_symbols
            
            ticker_dict = {t['symbol']: t for t in tickers if t['symbol'] in usdt_symbols}
            
            # Get book tickers (bid/ask prices) - single batch request
            book_tickers = await binance_client.get_book_tickers()
            if not book_tickers:
                logger.error("❌ [UniverseSelector] Failed to get book tickers")
                return self.selected_symbols
            
            book_ticker_dict = {bt['symbol']: bt for bt in book_tickers if bt['symbol'] in usdt_symbols}
            logger.info(f"📊 [UniverseSelector] Fetched book tickers (bid/ask) for {len(book_ticker_dict)} symbols")
            
            # STAGE 1: Filter by 24h volume (in-memory, no API calls)
            stage1_start = datetime.now()
            stage1_symbols = await self._filter_by_volume(usdt_symbols, ticker_dict, book_ticker_dict)
            stage1_elapsed = (datetime.now() - stage1_start).total_seconds()
            logger.info(f"✅ [Stage 1/3] Volume filter: {len(usdt_symbols)} → {len(stage1_symbols)} symbols ({stage1_elapsed:.2f}s)")
            
            if not stage1_symbols:
                logger.warning("⚠️ [UniverseSelector] No symbols passed volume filter")
                return self.selected_symbols
            
            # STAGE 2: Filter by open interest (throttled API calls with semaphore)
            stage2_start = datetime.now()
            stage2_symbols = await self._filter_by_open_interest(stage1_symbols, ticker_dict)
            stage2_elapsed = (datetime.now() - stage2_start).total_seconds()
            logger.info(f"✅ [Stage 2/3] Open Interest filter: {len(stage1_symbols)} → {len(stage2_symbols)} symbols ({stage2_elapsed:.2f}s)")
            
            if not stage2_symbols:
                logger.warning("⚠️ [UniverseSelector] No symbols passed open interest filter")
                return self.selected_symbols
            
            # STAGE 3: Filter by spread (using already fetched ticker data)
            stage3_start = datetime.now()
            final_symbols = await self._filter_by_spread(stage2_symbols, ticker_dict)
            stage3_elapsed = (datetime.now() - stage3_start).total_seconds()
            logger.info(f"✅ [Stage 3/3] Spread filter: {len(stage2_symbols)} → {len(final_symbols)} symbols ({stage3_elapsed:.2f}s)")
            
            if not final_symbols:
                logger.warning("⚠️ [UniverseSelector] No symbols passed spread filter")
                return self.selected_symbols
            
            # Calculate scores for ALL symbols that passed filters
            logger.info(f"📊 [UniverseSelector] Calculating scores for {len(final_symbols)} symbols...")
            scored_symbols = []
            for symbol_data in final_symbols:
                score = await self.calculate_symbol_score(symbol_data)
                symbol_data['score'] = score
                scored_symbols.append(symbol_data)
            logger.info(f"✅ [UniverseSelector] Score calculation complete")
            
            # Sort by score (best first) but use ALL symbols, no artificial limit
            scored_symbols.sort(key=lambda x: x['score'], reverse=True)
            top_symbols = scored_symbols  # Use ALL symbols that passed filters
            self.selected_symbols = [s['symbol'] for s in top_symbols]
            logger.info(f"📊 [UniverseSelector] Updating database with {len(top_symbols)} symbols...")
            
            # Update database
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
    
    async def _filter_by_volume(self, symbols: List[str], ticker_dict: Dict, book_ticker_dict: Dict) -> List[Dict]:
        """Stage 1: Filter by 24h volume (in-memory, no API calls)"""
        filtered = []
        logged_first_book = False
        no_book_ticker_count = 0
        
        for symbol in symbols:
            ticker = ticker_dict.get(symbol)
            if not ticker:
                continue
            
            volume_24h = float(ticker.get('quoteVolume', 0))
            if volume_24h < Config.MIN_24H_VOLUME:
                continue
            
            # Get bid/ask from book ticker
            book_ticker = book_ticker_dict.get(symbol)
            if not book_ticker:
                no_book_ticker_count += 1
                continue
            
            # Log first book ticker to confirm structure
            if not logged_first_book:
                logger.info(f"📝 [Stage 1 Debug] First book ticker ({symbol}): bidPrice={book_ticker.get('bidPrice')}, askPrice={book_ticker.get('askPrice')}")
                logged_first_book = True
            
            bid_price = float(book_ticker.get('bidPrice', 0))
            ask_price = float(book_ticker.get('askPrice', 0))
            
            filtered.append({
                'symbol': symbol,
                'volume_24h': volume_24h,
                'trades_24h': int(ticker.get('count', 0)),
                'price_change_percent': float(ticker.get('priceChangePercent', 0)),
                'bid_price': bid_price,
                'ask_price': ask_price
            })
        
        if no_book_ticker_count > 0:
            logger.info(f"📊 [Stage 1] Skipped {no_book_ticker_count} symbols without book ticker data")
        
        # Limit to TOP 40 symbols by volume to avoid API request limits and speed up Stage 2
        if len(filtered) > 40:
            passed_count = len(filtered)
            filtered_sorted = sorted(filtered, key=lambda x: x.get('volume_24h', 0), reverse=True)
            filtered = filtered_sorted[:40]
            logger.info(f"🔝 [Stage 1] Limited to TOP-40 symbols by 24h volume (from {passed_count} to {len(filtered)})")
        
        return filtered
    
    async def _filter_by_open_interest(self, symbols: List[Dict], ticker_dict: Dict) -> List[Dict]:
        """Stage 2: Filter by open interest (BATCHED requests for stability)"""
        passed_count = 0
        failed_count = 0
        below_threshold_count = 0
        
        oi_samples = []  # Track first 5 OI values for logging
        results = []
        
        # Split symbols into batches of 20
        BATCH_SIZE = 20
        batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
        total_batches = len(batches)
        
        logger.info(f"📊 [Stage 2] Processing {len(symbols)} symbols in {total_batches} batches of {BATCH_SIZE} (stable mode)...")
        
        for batch_idx, batch in enumerate(batches, 1):
            logger.info(f"🔄 [Stage 2 Batch {batch_idx}/{total_batches}] Processing symbols {(batch_idx-1)*BATCH_SIZE + 1} to {min(batch_idx*BATCH_SIZE, len(symbols))}...")
            
            for symbol_data in batch:
                try:
                    oi_data = await binance_client.get_open_interest(symbol_data['symbol'])
                    if oi_data and oi_data.get('openInterest'):
                        open_interest = float(oi_data.get('openInterest', 0))
                        
                        # Use lastPrice from ticker data (already loaded, no extra API call)
                        ticker = ticker_dict.get(symbol_data['symbol'])
                        if ticker:
                            last_price = float(ticker.get('lastPrice', 0))
                            if last_price > 0:
                                oi_value = open_interest * last_price
                                
                                # Log first 5 OI values for debugging
                                if len(oi_samples) < 5:
                                    oi_samples.append({
                                        'symbol': symbol_data['symbol'],
                                        'oi_value': oi_value,
                                        'last_price': last_price,
                                        'oi_contracts': open_interest
                                    })
                                
                                if oi_value >= Config.MIN_OPEN_INTEREST:
                                    symbol_data['open_interest'] = oi_value
                                    symbol_data['mark_price'] = last_price
                                    passed_count += 1
                                    results.append(symbol_data)
                                else:
                                    below_threshold_count += 1
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.debug(f"Failed to fetch OI for {symbol_data['symbol']}: {e}")
                
                # Small delay between individual requests (0.3s for faster Stage 2)
                await asyncio.sleep(0.3)
            
            # Longer pause between batches to avoid overwhelming system
            if batch_idx < total_batches:
                logger.info(f"⏸️  [Stage 2] Batch {batch_idx}/{total_batches} complete, pausing 1 second before next batch...")
                await asyncio.sleep(1)
        
        # Log sample OI values for debugging
        if oi_samples:
            sample_str = ', '.join([f"{s['symbol']}(${s['oi_value']/1e6:.1f}M @ ${s['last_price']:.2f})" for s in oi_samples])
            logger.info(f"📊 [Stage 2 Samples] First 5 OI values: {sample_str}")
        
        logger.info(f"📊 [Stage 2 Summary] Processed {len(symbols)} symbols: Passed={passed_count}, Below threshold={below_threshold_count}, Failed={failed_count}")
        
        return results
    
    async def _filter_by_spread(self, symbols: List[Dict], ticker_dict: Dict) -> List[Dict]:
        """Stage 3: Filter by spread with optional dynamic ATR-based filter"""
        filtered = []
        spread_samples = []  # Track first 5 spread values for debugging
        no_bid_count = 0
        passed_count = 0
        filtered_count = 0
        
        for symbol_data in symbols:
            bid_price = symbol_data.get('bid_price', 0)
            ask_price = symbol_data.get('ask_price', 0)
            
            if bid_price <= 0:
                no_bid_count += 1
                logger.debug(f"[{symbol_data['symbol']}] No bid price: bid={bid_price}, ask={ask_price}")
                continue
            
            spread = (ask_price - bid_price) / bid_price
            
            # Log first 5 spread values for debugging
            if len(spread_samples) < 5:
                spread_samples.append({
                    'symbol': symbol_data['symbol'],
                    'bid': bid_price,
                    'ask': ask_price,
                    'spread': spread,
                    'spread_pct': spread * 100
                })
            
            # Calculate dynamic spread threshold if enabled
            max_spread = Config.MAX_SPREAD
            if Config.USE_DYNAMIC_SPREAD:
                try:
                    dynamic_spread = await self._calculate_dynamic_spread(symbol_data['symbol'], symbol_data.get('mark_price', bid_price))
                    if dynamic_spread > 0:
                        max_spread = min(Config.MAX_SPREAD, dynamic_spread)
                except Exception as e:
                    logger.debug(f"Failed to calculate dynamic spread for {symbol_data['symbol']}: {e}")
            
            if spread <= max_spread:
                symbol_data['spread'] = spread
                filtered.append(symbol_data)
                passed_count += 1
            else:
                filtered_count += 1
        
        # Log spread samples
        if spread_samples:
            sample_str = ', '.join([f"{s['symbol']}({s['spread_pct']:.4f}%)" for s in spread_samples])
            logger.info(f"📊 [Stage 3 Samples] First 5 spreads: {sample_str}")
        
        logger.info(f"📊 [Stage 3 Details] Passed: {passed_count}, Filtered: {filtered_count}, No bid: {no_bid_count}, Max spread: {Config.MAX_SPREAD*100:.2f}%")
        
        return filtered
    
    async def _calculate_dynamic_spread(self, symbol: str, mark_price: float) -> float:
        """Calculate dynamic spread threshold based on ATR"""
        try:
            # Get 15min klines for last 24h (96 candles)
            klines = await binance_client.get_klines(symbol, interval='15m', limit=96)
            if not klines or len(klines) < 14:
                return 0
            
            # Calculate ATR (Average True Range)
            true_ranges = []
            for i in range(1, len(klines)):
                high = float(klines[i][2])
                low = float(klines[i][3])
                prev_close = float(klines[i-1][4])
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            if not true_ranges:
                return 0
            
            atr = np.mean(true_ranges[-14:])  # ATR(14)
            
            if atr <= 0 or mark_price <= 0:
                return 0
            
            # Dynamic spread = ATR_MULTIPLIER * (ATR / price)
            dynamic_spread = Config.DYNAMIC_SPREAD_ATR_MULTIPLIER * (atr / mark_price)
            
            logger.debug(f"[{symbol}] ATR-based spread: {dynamic_spread:.6f} (ATR={atr:.4f}, price={mark_price:.2f})")
            
            return dynamic_spread
            
        except Exception as e:
            logger.debug(f"Error calculating ATR for {symbol}: {e}")
            return 0
    
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
