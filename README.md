# Binance Futures Scanner Bot 🚀

High-performance Telegram bot for 24/7 scanning of Binance futures market with real-time orderbook analysis, large trade detection, and automated signal generation.

## 🎯 Features

### Core Functionality
- **24/7 Market Scanning**: Continuous analysis of Binance Futures market (coin/USDT pairs)
- **Real-time Order Book Analysis**: Detects imbalance >0.28 threshold
- **Large Trade Detection**: Identifies trades >$50,000 USD
- **Automated Signal Generation**: LONG/SHORT signals with quality classification (HIGH/MEDIUM/LOW)
- **Smart Risk Management**: Max 80 signals/day, max 5 concurrent, correlation checks
- **Signal Tracking**: Monitors SL/TP levels every minute with automatic closure
- **Telegram Integration**: Sends signals and updates via Telegram with /status and /stats commands

### Technical Features
- **Proxy Support**: All requests via proxy 23.27.184.165:5766
- **Internal Rate Limiter**: Weight-based calculation with auto-correction from Binance headers
- **PostgreSQL Storage**: Signals, trades, metrics, and daily statistics
- **Redis Caching**: Real-time market data (with in-memory fallback)
- **WebSocket Data Collection**: Orderbook depth, aggregate trades, klines
- **Detailed Logging**: All operations logged for debugging and monitoring

## 📊 Signal Quality Classification

| Priority | Quality Score | Max Daily | Hold Time | Description |
|----------|---------------|-----------|-----------|-------------|
| HIGH | 80-100 | 20 signals | 15-45 min | Strong orderbook imbalance + high volume + multiple large trades |
| MEDIUM | 65-79 | 40 signals | 30-90 min | Moderate signals with good confirmation |
| LOW | 50-64 | 20 signals | 60-180 min | Weaker signals, lower confidence |

## 🏗️ Project Structure

```
bot/
├── config/          # Configuration settings
│   └── config.py    # All configuration parameters
├── database/        # Database models and manager
│   ├── models.py    # SQLAlchemy models (Signal, Trade, Symbol, etc.)
│   └── db_manager.py # Database connection and session management
├── utils/           # Utility modules
│   ├── logger.py    # Logging configuration
│   ├── rate_limiter.py # API rate limiting with weight calculation
│   ├── binance_client.py # Binance API client with proxy support
│   └── redis_manager.py # Redis caching (with fallback)
├── modules/         # Core analysis modules
│   ├── universe_selector.py # Dynamic coin selection every 6 hours
│   ├── orderbook_analyzer.py # Order book imbalance detection
│   ├── trade_flow_analyzer.py # Large trades analysis (5-min window)
│   ├── signal_generator.py # Signal generation with quality scoring
│   ├── risk_manager.py # Risk limits and correlation checks
│   ├── telegram_dispatcher.py # Telegram message sending
│   ├── signal_tracker.py # SL/TP monitoring every minute
│   ├── data_collector.py # WebSocket data collection
│   └── performance_monitor.py # Win rate, PnL, Sharpe ratio tracking
├── main.py          # Main bot orchestration (24/7 operation)
└── telegram_bot.py  # Telegram command handlers (/status, /stats)
```

## 🚀 Quick Start

### 1. Prerequisites

All dependencies are already installed in this Replit environment:
- Python 3.11+
- PostgreSQL database (configured)
- Redis (optional, has in-memory fallback)
- Required packages: python-binance, python-telegram-bot, psycopg2-binary, redis, websockets, etc.

### 2. Environment Variables

The following secrets are already configured in Replit Secrets:
```
BINANCE_API_KEY=<your_binance_api_key>
BINANCE_API_SECRET=<your_binance_api_secret>
TELEGRAM_BOT_TOKEN=<your_telegram_bot_token>
TELEGRAM_CHAT_ID=<your_telegram_chat_id>
DATABASE_URL=<postgresql_connection_string>
```

### 3. Initialize Database

Run once to create all necessary tables:
```bash
python3 init_db.py
```

### 4. Test Connections

Verify Binance API and Telegram bot connectivity:
```bash
python3 test_binance_telegram.py
```

Expected output:
```
✅ Binance API connected! Server time: 1761603636610
✅ BTC/USDT price: $114,432.90
✅ Telegram bot connected and test message sent!
✅ ALL TESTS PASSED! Bot is ready to run.
```

### 5. Run the Bot

Start the bot in 24/7 mode:
```bash
python3 run.py
```

The bot will:
1. Initialize all modules (DB, Binance API, Telegram, Redis)
2. Perform initial universe scan (select top symbols)
3. Send startup notification to Telegram
4. Start continuous loops:
   - Universe rescan every 6 hours
   - Signal generation loop (checks every minute)
   - Signal tracking loop (monitors SL/TP every minute)
   - Metrics update loop (calculates daily stats every hour)

## 📱 Telegram Commands

- `/status` - Shows current bot status (running, analyzed symbols, open signals)
- `/stats` - Displays detailed daily statistics (signals, win rate, PnL, TP/SL hits)

## 📈 Signal Format

Example signal message sent to Telegram:

```
🟢 🔥 **HIGH PRIORITY LONG SIGNAL**

📊 **Symbol:** BTCUSDT
💰 **Entry:** $114,432.90
🛑 **Stop Loss:** $112,144.24
🎯 **TP1:** $116,721.56
🎯 **TP2:** $117,866.09

📈 **Quality Score:** 85.2/100
⚖️ **Orderbook Imbalance:** 0.342
🔢 **Large Trades:** 5
📊 **Volume Intensity:** 2.45x
💪 **Confidence:** 87.5%

💼 **Position Size:** 1.0%
📊 **R:R Ratio:** 1.02
⏱️ **Expected Hold:** 15-45min

🆔 Signal ID: `a1b2c3d4-...`
⏰ 2025-10-27 22:15:30
```

## 🔧 Configuration

All settings are in `bot/config/config.py`:

### Universe Selection
- `MIN_24H_VOLUME`: $50,000,000 minimum 24h volume
- `MIN_OPEN_INTEREST`: $10,000,000 minimum open interest
- `MAX_SPREAD`: 0.02% maximum spread
- `UNIVERSE_RESCAN_INTERVAL`: 6 hours

### Signal Detection
- `ORDERBOOK_IMBALANCE_THRESHOLD`: 0.28 (28% imbalance required)
- `MIN_LARGE_TRADES`: 3 large trades minimum
- `LARGE_TRADE_SIZE`: $50,000 per trade
- `VOLUME_CONFIRMATION_MULTIPLIER`: 1.8x average volume

### Risk Management
- `MAX_DAILY_SIGNALS`: 80 signals maximum per day
- `MAX_CONCURRENT_SIGNALS`: 5 signals open at once
- `CORRELATION_THRESHOLD`: 0.6 maximum correlation between signals

### Priority Levels
- **HIGH**: Max 20/day, 80+ quality score, 15-45 min hold time
- **MEDIUM**: Max 40/day, 65+ quality score, 30-90 min hold time
- **LOW**: Max 20/day, 50+ quality score, 60-180 min hold time

## 📊 Database Schema

### Signals Table
Stores all generated signals:
- `id`: UUID primary key
- `symbol`: Trading pair (e.g., BTCUSDT)
- `direction`: LONG or SHORT
- `priority`: HIGH, MEDIUM, or LOW
- `entry_price`, `stop_loss`, `take_profit_1`, `take_profit_2`
- `quality_score`: 0-100 signal quality
- `orderbook_imbalance`, `large_trades_count`, `volume_intensity`
- `status`: OPEN or CLOSED
- `telegram_message_id`: For reply messages

### Trades Table
Stores closed signal outcomes:
- `signal_id`: References signals table
- `exit_price`, `exit_reason`: Actual exit details
- `pnl_percent`: Profit/loss percentage
- `hold_time_minutes`: Actual hold time
- `entry_time`, `exit_time`: Timestamps

### Symbol Table
Tracks analyzed symbols:
- `symbol`: Trading pair
- `score`: Universe selection score
- `volume_24h`, `open_interest`, `spread`, `trades_24h`
- `is_active`: Currently in universe

### PerformanceMetrics Table
Daily performance statistics:
- `date`: Date of metrics
- `signals_generated`, `signals_triggered`: Counts
- `win_count`, `loss_count`, `win_rate`
- `total_pnl`, `average_pnl`, `max_profit`, `max_loss`
- `sharpe_ratio`, `max_drawdown`
- `tp1_hit_count`, `tp2_hit_count`, `sl_hit_count`

## 🔍 How It Works

### 1. Universe Selection (Every 6 hours)
1. Fetch all Binance Futures symbols
2. Filter by volume ($50M+), open interest ($10M+), spread (<0.02%)
3. Calculate score based on:
   - Volume (30%)
   - Liquidity (25%)
   - Volatility (25%)
   - Activity (20%)
4. Select top symbols
5. Send update notification to Telegram

### 2. Signal Generation (Continuous)
1. Monitor orderbook imbalance via WebSocket
2. Track large trades (>$50k) in 5-minute window
3. Check conditions:
   - **LONG**: Imbalance >0.28, large buys ≥3, volume >1.8x average
   - **SHORT**: Imbalance <-0.28, large sells ≥3, volume >1.8x average
4. Calculate quality score (0-100)
5. Check risk limits (daily, concurrent, correlation)
6. Generate signal with SL/TP levels
7. Save to database and send to Telegram

### 3. Signal Tracking (Every Minute)
1. Fetch current price for all open signals
2. Check if price hit SL, TP1, or TP2
3. If hit:
   - Close signal in database
   - Create trade record
   - Send update message to Telegram (reply to original)
   - Calculate hold time and PnL

### 4. Performance Monitoring (Every Hour)
1. Calculate daily metrics:
   - Win rate (wins / total trades)
   - Total PnL
   - Sharpe ratio
   - Max drawdown
   - TP/SL hit rates
2. Save to PerformanceMetrics table

## 🛠️ Troubleshooting

### Redis Connection Issues
If Redis fails to connect, the bot automatically falls back to in-memory caching. This is normal in some environments. The bot will work without Redis, but without persistent caching between restarts.

### Binance API Rate Limits
The bot includes internal rate limiting with weight calculation. If you see rate limit warnings:
- The bot will automatically pause and retry
- Check `bot/logs/bot.log` for details
- Rate limits are tracked via `X-MBX-USED-WEIGHT-1M` header

### Database Connection
If database connection fails:
1. Check `DATABASE_URL` environment variable
2. Run `python3 init_db.py` to recreate tables
3. Verify PostgreSQL is running

### Telegram Bot Not Responding
1. Verify `TELEGRAM_BOT_TOKEN` is correct
2. Check `TELEGRAM_CHAT_ID` matches your chat
3. Run `python3 test_binance_telegram.py` to test connection

## 📝 Logs

All operations are logged to:
- Console output (INFO level and above)
- `bot/logs/bot.log` (detailed logging)

Log format:
```
2025-10-27 22:20:37 - BinanceScanner - INFO - [telegram_dispatcher.py:24] - ✅ [TelegramDispatcher] Connected as @EBinFut_bot
```

## ⚠️ Important Notes

1. **No Simplifications**: This is a full implementation as per technical specification
2. **Proxy Mandatory**: All Binance requests go through 23.27.184.165:5766
3. **Signal Tracking**: Every 60 seconds to ensure accurate win rate statistics
4. **Reply Messages**: Telegram sends closure updates as replies to original signals
5. **Rate Limiting**: Internal weight-based limiter with auto-correction
6. **No Mock Data**: All data is real-time from Binance API

## 📄 License

This project is for educational and research purposes only. Use at your own risk. Not financial advice.

## 🤝 Support

For issues or questions:
1. Check `bot/logs/bot.log` for errors
2. Run `python3 test_binance_telegram.py` to verify connections
3. Use `/status` command in Telegram to check bot health
