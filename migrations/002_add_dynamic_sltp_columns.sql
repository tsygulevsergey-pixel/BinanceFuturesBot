-- Migration: Add dynamic SL/TP reasoning columns
-- Version: 002
-- Date: 2025-10-31
-- Description: Adds columns for storing orderbook-based dynamic SL/TP levels and reasoning

-- Step 1: Add dynamic SL/TP reasoning columns to signals table
ALTER TABLE signals 
ADD COLUMN IF NOT EXISTS stop_loss_reason VARCHAR(200),
ADD COLUMN IF NOT EXISTS tp1_reason VARCHAR(200),
ADD COLUMN IF NOT EXISTS tp2_reason VARCHAR(200),
ADD COLUMN IF NOT EXISTS support_level NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS resistance_level NUMERIC(20, 8);

-- Step 2: Add dynamic SL/TP reasoning columns to trades table
ALTER TABLE trades
ADD COLUMN IF NOT EXISTS stop_loss_reason VARCHAR(200),
ADD COLUMN IF NOT EXISTS tp1_reason VARCHAR(200),
ADD COLUMN IF NOT EXISTS tp2_reason VARCHAR(200),
ADD COLUMN IF NOT EXISTS support_level NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS resistance_level NUMERIC(20, 8);

-- Verify migration
SELECT 
    column_name, 
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'signals' 
    AND column_name IN ('stop_loss_reason', 'tp1_reason', 'tp2_reason', 'support_level', 'resistance_level')
ORDER BY column_name;

SELECT 
    column_name, 
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'trades' 
    AND column_name IN ('stop_loss_reason', 'tp1_reason', 'tp2_reason', 'support_level', 'resistance_level')
ORDER BY column_name;
