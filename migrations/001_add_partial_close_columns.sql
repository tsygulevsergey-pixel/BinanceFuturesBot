-- Migration: Add partial close tracking columns
-- Version: 001
-- Date: 2025-10-31
-- Description: Adds columns for 50/50 partial close (TP1/TP2) with breakeven SL functionality

-- Step 1: Add partial close tracking columns to signals table
ALTER TABLE signals 
ADD COLUMN IF NOT EXISTS tp1_hit_price NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS tp1_hit_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS tp1_pnl NUMERIC(10, 4),
ADD COLUMN IF NOT EXISTS tp2_hit_price NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS tp2_hit_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS tp2_pnl NUMERIC(10, 4),
ADD COLUMN IF NOT EXISTS partial_close_status VARCHAR(20) DEFAULT 'NONE',
ADD COLUMN IF NOT EXISTS breakeven_moved BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS current_stop_loss NUMERIC(20, 8);

-- Step 2: Add partial close tracking columns to trades table
ALTER TABLE trades
ADD COLUMN IF NOT EXISTS tp1_hit_price NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS tp1_hit_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS tp1_pnl NUMERIC(10, 4),
ADD COLUMN IF NOT EXISTS tp2_hit_price NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS tp2_hit_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS tp2_pnl NUMERIC(10, 4),
ADD COLUMN IF NOT EXISTS partial_close_status VARCHAR(20);

-- Step 3: Extend exit_reason column to support new exit reasons
ALTER TABLE trades ALTER COLUMN exit_reason TYPE VARCHAR(30);

-- Verify migration
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'signals' 
    AND column_name IN ('tp1_hit_price', 'tp2_hit_price', 'partial_close_status', 'breakeven_moved', 'current_stop_loss')
ORDER BY column_name;

SELECT 
    column_name, 
    data_type, 
    character_maximum_length
FROM information_schema.columns 
WHERE table_name = 'trades' 
    AND column_name = 'exit_reason';
