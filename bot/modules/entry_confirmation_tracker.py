"""
Entry Confirmation Tracker - prevents signal creation on temporary spikes

Requires SUSTAINED confluence of all 4 factors for 5 seconds before creating signal:
1. Orderbook imbalance > threshold
2. Large trades >= min count
3. Volume intensity > multiplier
4. Price vs VWAP confirmation

If ANY condition fails → counter resets to 0
Only after 50 consecutive samples (5 seconds) → signal is created
"""
import logging
from typing import Dict, Optional
from bot.config import Config

logger = logging.getLogger(__name__)


class EntryConfirmationTracker:
    """Tracks entry confirmation counters per symbol to filter noise"""
    
    def __init__(self):
        self.confirmation_counters: Dict[str, int] = {}  # {symbol: counter}
        self.persistence_threshold = Config.SIGNAL_ENTRY_PERSISTENCE_SAMPLES
        
        logger.info(
            f"🎯 [EntryConfirmationTracker] Initialized with "
            f"{self.persistence_threshold} samples ({self.persistence_threshold * 0.1:.1f}s) threshold"
        )
    
    def check_and_update(
        self, 
        symbol: str, 
        all_conditions_met: bool
    ) -> bool:
        """
        Check if signal should be created based on persistence
        
        Args:
            symbol: Trading symbol
            all_conditions_met: Whether all 4 confluence factors are satisfied
            
        Returns:
            True if confirmation threshold reached (create signal), False otherwise
        """
        # Initialize counter if not exists
        if symbol not in self.confirmation_counters:
            self.confirmation_counters[symbol] = 0
        
        if all_conditions_met:
            # Increment confirmation counter
            self.confirmation_counters[symbol] += 1
            counter = self.confirmation_counters[symbol]
            
            if counter >= self.persistence_threshold:
                # Threshold reached - CONFIRMED SIGNAL!
                logger.info(
                    f"✅ [EntryConfirmationTracker] {symbol}: CONFIRMED after "
                    f"{counter} samples ({counter * 0.1:.1f}s) → CREATE SIGNAL"
                )
                # Reset counter after signal creation
                self.confirmation_counters[symbol] = 0
                return True
            else:
                # Still building confirmation
                if counter % 10 == 0:  # Log every second to reduce spam
                    logger.debug(
                        f"📊 [EntryConfirmationTracker] {symbol}: Building confirmation "
                        f"{counter}/{self.persistence_threshold} ({counter * 0.1:.1f}s)"
                    )
                return False
        else:
            # Conditions NOT met - RESET counter
            old_counter = self.confirmation_counters[symbol]
            if old_counter > 0:
                logger.info(
                    f"🔄 [EntryConfirmationTracker] {symbol}: Conditions failed, "
                    f"RESET counter from {old_counter} → 0"
                )
                self.confirmation_counters[symbol] = 0
            return False
    
    def get_counter(self, symbol: str) -> int:
        """Get current confirmation counter for symbol"""
        return self.confirmation_counters.get(symbol, 0)
    
    def reset_counter(self, symbol: str):
        """Manually reset counter for symbol"""
        if symbol in self.confirmation_counters:
            logger.debug(f"🔄 [EntryConfirmationTracker] Manual reset for {symbol}")
            self.confirmation_counters[symbol] = 0
    
    def cleanup_inactive_symbols(self, active_symbols: list):
        """Remove counters for symbols no longer in active universe"""
        current_symbols = set(self.confirmation_counters.keys())
        active_set = set(active_symbols)
        
        inactive = current_symbols - active_set
        if inactive:
            for symbol in inactive:
                del self.confirmation_counters[symbol]
            logger.info(
                f"🧹 [EntryConfirmationTracker] Cleaned up {len(inactive)} "
                f"inactive symbols: {inactive}"
            )
