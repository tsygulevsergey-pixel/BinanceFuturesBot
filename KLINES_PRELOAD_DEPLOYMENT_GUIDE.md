# Historical Klines Preloading - Deployment Guide

## Overview
This update adds historical klines preloading from Binance API to eliminate the 20-30 minute wait for ATR calculation on bot restart. The bot now fetches the last 30 1-minute candles for each symbol at startup and stores them in a new PostgreSQL table.

## Changes Made

### 1. Database Model
- **File**: `bot/database/models.py`
- **Changes**: Added `Kline` model to store historical candlestick data
  - Fields: symbol, interval, timestamp, open, high, low, close, volume
  - Unique constraint on (symbol, interval, timestamp) to prevent duplicates

### 2. Database Migration
- **File**: `migrations/003_create_klines_table.sql`
- **Changes**: Creates `klines` table with:
  - UNIQUE constraint on (symbol, interval, timestamp)
  - Indexes for efficient querying by (symbol, interval, timestamp)

### 3. Preload Logic
- **File**: `bot/main.py`
- **Changes**: 
  - Added `preload_historical_klines()` method
  - Fetches last 30 1m candles from Binance API for each active symbol
  - Uses UPSERT (INSERT ... ON CONFLICT DO NOTHING) to avoid duplicates
  - Called after initial universe scan, before starting data collection

## Deployment Steps

### Step 1: Pull Latest Code
```bash
cd /root/BinanceFuturesBot
git pull origin main
```

### Step 2: Run Database Migration
```bash
# Apply migration 003
psql "$DATABASE_URL" -f migrations/003_create_klines_table.sql
```

**Expected Output**:
```
CREATE TABLE
CREATE INDEX
CREATE INDEX
```

### Step 3: Verify Migration
```bash
# Check that klines table exists with correct schema
psql "$DATABASE_URL" -c "\d klines"
```

**Expected Output**:
```
                           Table "public.klines"
   Column   |         Type          | Collation | Nullable |      Default       
------------+-----------------------+-----------+----------+--------------------
 id         | integer               |           | not null | nextval('klines...')
 symbol     | character varying(20) |           | not null | 
 interval   | character varying(10) |           | not null | 
 timestamp  | timestamp             |           | not null | 
 open       | numeric(20,8)         |           | not null | 
 high       | numeric(20,8)         |           | not null | 
 low        | numeric(20,8)         |           | not null | 
 close      | numeric(20,8)         |           | not null | 
 volume     | numeric(20,2)         |           | not null | 
 created_at | timestamp             |           |          | now()
Indexes:
    "klines_pkey" PRIMARY KEY, btree (id)
    "klines_symbol_interval_timestamp_key" UNIQUE CONSTRAINT, btree (symbol, interval, "timestamp")
    "idx_kline_symbol_interval_time" btree (symbol, interval, "timestamp" DESC)
    "idx_kline_timestamp" btree ("timestamp" DESC)
```

### Step 4: Restart Bot
```bash
sudo systemctl restart binance-bot
```

### Step 5: Verify Preload
```bash
# Check logs for preload activity
sudo tail -f /var/log/binance-bot-error.log | grep -i "preload"
```

**Expected Log Messages**:
```
📥 [Main] Preloading historical klines for X symbols...
✅ [Main] Loaded 30 klines for BTCUSDT
✅ [Main] Loaded 30 klines for ETHUSDT
...
✅ [Main] Preloaded 900 klines for 30/30 symbols
```

### Step 6: Verify Database Data
```bash
# Check that klines were inserted
psql "$DATABASE_URL" -c "SELECT symbol, COUNT(*) FROM klines GROUP BY symbol ORDER BY symbol;"
```

**Expected Output** (for each symbol):
```
  symbol   | count 
-----------+-------
 BTCUSDT   |    30
 ETHUSDT   |    30
 ...
```

### Step 7: Verify ATR Calculation
```bash
# Check logs for ATR calculation (should happen immediately, not after 20 minutes)
sudo tail -f /var/log/binance-bot-error.log | grep -i "ATR"
```

**Expected**: ATR calculations should start immediately after preload completes.

## Troubleshooting

### Issue: Migration fails with "relation already exists"
**Solution**: Table already exists, skip Step 2 and proceed to Step 3 to verify schema.

### Issue: No klines data inserted
**Possible Causes**:
1. Binance API rate limit hit
2. Network connectivity issues
3. Invalid symbols in universe

**Check**:
```bash
# Look for error messages during preload
sudo tail -f /var/log/binance-bot-error.log | grep -i "failed to load klines"
```

### Issue: Duplicate klines on restart
**Cause**: Missing UNIQUE constraint or old migration version
**Solution**: 
```bash
# Drop table and recreate with correct schema
psql "$DATABASE_URL" -c "DROP TABLE IF EXISTS klines;"
psql "$DATABASE_URL" -f migrations/003_create_klines_table.sql
```

### Issue: ATR still not calculating
**Possible Causes**:
1. Less than 14 klines available (minimum for ATR)
2. VolatilityCalculator not reading from klines table

**Check**:
```bash
# Verify klines count per symbol
psql "$DATABASE_URL" -c "SELECT symbol, COUNT(*) FROM klines GROUP BY symbol HAVING COUNT(*) < 14;"
```

If any symbols have < 14 klines, manually load more:
```bash
# In Python REPL or script
await binance_client.get_klines('BTCUSDT', '1m', limit=30)
```

## Rollback Instructions

If you need to rollback this update:

### Step 1: Stop Bot
```bash
sudo systemctl stop binance-bot
```

### Step 2: Revert Code
```bash
cd /root/BinanceFuturesBot
git reset --hard <previous_commit_hash>
```

### Step 3: Drop Klines Table (Optional)
```bash
psql "$DATABASE_URL" -c "DROP TABLE IF EXISTS klines;"
```

### Step 4: Restart Bot
```bash
sudo systemctl start binance-bot
```

## Performance Impact

- **Initial preload time**: ~5-10 seconds for 30 symbols (1-2 API calls per second)
- **Database size impact**: ~30 rows per symbol (negligible)
- **ATR calculation**: Immediate (no 20-minute wait)
- **Bot restart time**: +5-10 seconds (acceptable for 20-minute gain)

## Verification Checklist

- [ ] Migration 003 applied successfully
- [ ] Klines table exists with UNIQUE constraint
- [ ] Bot restarted without errors
- [ ] Preload logs show successful data fetching
- [ ] Database contains 30 klines per symbol
- [ ] ATR calculations start immediately
- [ ] No duplicate klines on restart

## Notes

- Preload runs **after** initial universe scan, so only active symbols are loaded
- UPSERT logic ensures idempotent restarts (no duplicates)
- Failed symbol loads are logged but don't stop the preload process
- Klines are stored in UTC timestamp format (Binance default)
