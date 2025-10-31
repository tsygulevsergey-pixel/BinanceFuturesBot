-- Migration: Create klines table for historical candlestick data
-- Version: 003
-- Date: 2025-10-31
-- Description: Creates klines table to store historical price data for ATR/volatility calculations

-- Create klines table
CREATE TABLE IF NOT EXISTS klines (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    
    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(20, 2) NOT NULL,
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_kline_symbol_interval_time 
ON klines(symbol, interval, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_kline_timestamp 
ON klines(timestamp DESC);

-- Verify table creation
SELECT 
    column_name, 
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'klines'
ORDER BY ordinal_position;
