import asyncio
import aiohttp
import os

async def test_ticker():
    proxy_url = 'http://fyplvqgw:04azcek13s9n@23.27.184.165:5766'
    
    async with aiohttp.ClientSession() as session:
        url = 'https://fapi.binance.com/fapi/v1/ticker/24hr'
        params = {'symbol': 'BTCUSDT'}
        
        async with session.get(url, params=params, proxy=proxy_url, timeout=10) as response:
            ticker = await response.json()
            
            print("=== BTCUSDT 24hr Ticker Fields ===")
            for key, value in ticker.items():
                print(f"{key}: {value}")
            
            print("\n=== Checking bid/ask fields ===")
            print(f"bidPrice: {ticker.get('bidPrice', 'NOT FOUND')}")
            print(f"askPrice: {ticker.get('askPrice', 'NOT FOUND')}")
            print(f"lastPrice: {ticker.get('lastPrice', 'NOT FOUND')}")

if __name__ == '__main__':
    asyncio.run(test_ticker())
