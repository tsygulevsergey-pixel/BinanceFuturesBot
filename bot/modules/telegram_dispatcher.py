"""
Telegram Dispatcher - sends signals and notifications to Telegram
Sends signal details with all parameters, supports reply messages for signal updates
"""
import asyncio
from typing import Dict, Optional
from telegram import Bot
from telegram.error import TelegramError
from bot.config import Config
from bot.utils import logger

class TelegramDispatcher:
    def __init__(self):
        self.bot_token = Config.TELEGRAM_BOT_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.bot: Optional[Bot] = None
        
        logger.info(f"🔧 [TelegramDispatcher] Initialized with chat_id={self.chat_id}")
    
    async def initialize(self):
        try:
            # In v20.x, Bot() is async-ready by default
            self.bot = Bot(token=self.bot_token)
            
            # Test connection with async context manager
            async with self.bot:
                me = await self.bot.get_me()
                logger.info(f"✅ [TelegramDispatcher] Connected as @{me.username}")
        except Exception as e:
            logger.error(f"❌ [TelegramDispatcher] Failed to initialize bot: {e}")
            raise
    
    async def send_signal(self, signal: Dict) -> Optional[int]:
        if not self.bot:
            logger.error("❌ [TelegramDispatcher] Bot not initialized")
            return None
            
        try:
            direction_emoji = "🟢" if signal['direction'] == 'LONG' else "🔴"
            priority_emoji = {
                'HIGH': '🔥',
                'MEDIUM': '⚡',
                'LOW': '💡'
            }.get(signal['priority'], '📊')
            
            message = f"""
{direction_emoji} {priority_emoji} **{signal['priority']} PRIORITY {signal['direction']} SIGNAL**

📊 **Symbol:** {signal['symbol']}
💰 **Entry:** ${signal['entry_price']:.4f}
🛑 **Stop Loss:** ${signal['stop_loss']:.4f}
🎯 **TP1:** ${signal['take_profit_1']:.4f}
🎯 **TP2:** ${signal['take_profit_2']:.4f}

📈 **Quality Score:** {signal['quality_score']:.1f}/100
⚖️ **Orderbook Imbalance:** {signal['orderbook_imbalance']:.3f}
🔢 **Large Trades:** {signal['large_trades_count']}
📊 **Volume Intensity:** {signal['volume_intensity']:.2f}x
💪 **Confidence:** {signal['confidence']:.1%}

💼 **Position Size:** {signal['suggested_position_size']:.1%}
📊 **R:R Ratio:** {signal['risk_reward_ratio']:.2f}
⏱️ **Expected Hold:** {signal['expected_hold_time']}

🆔 Signal ID: `{signal['signal_id']}`
⏰ {signal['timestamp']}
"""
            
            # In v20.x, send_message() is async with context manager
            async with self.bot:
                sent_message = await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
            
            logger.info(f"📤 [TelegramDispatcher] Sent {signal['priority']} {signal['direction']} signal for {signal['symbol']}, message_id={sent_message.message_id}")
            
            return sent_message.message_id
            
        except Exception as e:
            logger.error(f"❌ [TelegramDispatcher] Error sending signal: {e}")
            return None
    
    async def send_signal_update(
        self,
        signal_id: str,
        symbol: str,
        exit_reason: str,
        entry_price: float,
        exit_price: float,
        pnl_percent: float,
        hold_time_minutes: int,
        original_message_id: Optional[int] = None,
        tp1_pnl: Optional[float] = None,
        tp2_pnl: Optional[float] = None
    ) -> bool:
        if not self.bot:
            logger.error("❌ [TelegramDispatcher] Bot not initialized")
            return False
            
        try:
            # Partial close messages
            if exit_reason == 'TAKE_PROFIT_1_PARTIAL':
                emoji = "🎯"
                message = f"""
{emoji} **TP1 HIT - PARTIAL CLOSE**

📊 **Symbol:** {symbol}
📍 **Entry:** ${entry_price:.4f}
📍 **TP1:** ${exit_price:.4f}
💰 **Closed 50%:** +{pnl_percent:.2f}%
🛡️ **SL → Breakeven** (entry price)
⏱️ **Hold Time:** {hold_time_minutes} minutes

🚀 **Waiting for TP2...** (remaining 50%)

🆔 Signal ID: `{signal_id}`
"""
            elif exit_reason == 'TAKE_PROFIT_2':
                emoji = "🎯🎯"
                tp1_str = f" (TP1: +{tp1_pnl:.2f}%)" if tp1_pnl is not None else ""
                tp2_str = f" (TP2: +{tp2_pnl:.2f}%)" if tp2_pnl is not None else ""
                message = f"""
{emoji} **TP2 HIT - FULLY CLOSED**

📊 **Symbol:** {symbol}
📍 **Entry:** ${entry_price:.4f}
📍 **TP2:** ${exit_price:.4f}
💰 **Total PnL:** +{pnl_percent:.2f}%{tp1_str}{tp2_str}
⏱️ **Hold Time:** {hold_time_minutes} minutes

✅ **Status:** FULLY CLOSED

🆔 Signal ID: `{signal_id}`
"""
            elif exit_reason == 'STOP_LOSS_BREAKEVEN':
                emoji = "🛡️"
                tp1_str = f" (TP1: +{tp1_pnl:.2f}%)" if tp1_pnl is not None else ""
                message = f"""
{emoji} **SL BREAKEVEN - PROFIT PROTECTED**

📊 **Symbol:** {symbol}
📍 **Entry/Exit:** ${entry_price:.4f}
💰 **Total PnL:** +{pnl_percent:.2f}%{tp1_str}
⏱️ **Hold Time:** {hold_time_minutes} minutes

✅ **Protected profit from TP1!**

🆔 Signal ID: `{signal_id}`
"""
            else:
                # Regular full close
                emoji = "✅" if pnl_percent > 0 else "❌"
                message = f"""
{emoji} **SIGNAL CLOSED**

📊 **Symbol:** {symbol}
📍 **Entry:** ${entry_price:.4f}
📍 **Exit:** ${exit_price:.4f}
💰 **PnL:** {pnl_percent:+.2f}%
🏁 **Reason:** {exit_reason}
⏱️ **Hold Time:** {hold_time_minutes} minutes

🆔 Signal ID: `{signal_id}`
"""
            
            # In v20.x, send_message() is async with context manager
            async with self.bot:
                if original_message_id:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode='Markdown',
                        reply_to_message_id=original_message_id
                    )
                else:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode='Markdown'
                    )
            
            logger.info(f"📤 [TelegramDispatcher] Sent signal update for {symbol}: {exit_reason} {pnl_percent:+.2f}%")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [TelegramDispatcher] Error sending signal update: {e}")
            return False
    
    async def send_notification(self, message: str) -> bool:
        if not self.bot:
            logger.error("❌ [TelegramDispatcher] Bot not initialized")
            return False
            
        try:
            # In v20.x, send_message() is async with context manager
            async with self.bot:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
            
            logger.info(f"📤 [TelegramDispatcher] Sent notification")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [TelegramDispatcher] Error sending notification: {e}")
            return False
    
    async def send_startup_message(self):
        message = """
🚀 **Binance Futures Scanner Bot Started**

✅ Bot is now running 24/7
🔍 Scanning futures market in real-time
📊 Analyzing orderbook and trade flow
🎯 Generating high-quality signals

Status: **ACTIVE**
"""
        return await self.send_notification(message)
    
    async def send_universe_update(self, symbol_count: int, top_symbols: list):
        top_list = ', '.join(top_symbols[:10])
        
        message = f"""
🔄 **Universe Updated**

📊 **Analyzing {symbol_count} symbols**

🏆 **Top 10:** {top_list}

⏰ Next update in 6 hours
"""
        return await self.send_notification(message)
    
    async def send_stats_message(self, stats: Dict):
        message = f"""
📊 **Daily Statistics**

🎯 **Signals Today:** {stats.get('total_signals', 0)}
🔥 **HIGH:** {stats.get('high_priority', 0)}
⚡ **MEDIUM:** {stats.get('medium_priority', 0)}
💡 **LOW:** {stats.get('low_priority', 0)}

✅ **Win Rate:** {stats.get('win_rate', 0):.1f}%
💰 **Total PnL:** {stats.get('total_pnl', 0):+.2f}%

🏁 **Exit Reasons:**
✨ **Imbalance Normalized:** {stats.get('imb_normalized_count', 0)}
🔄 **Imbalance Reversed:** {stats.get('imb_reversed_count', 0)}
🎯 **TP1 Hit:** {stats.get('tp1_count', 0)}
🎯 **TP2 Hit:** {stats.get('tp2_count', 0)}
🛑 **SL Hit:** {stats.get('sl_count', 0)}
"""
        return await self.send_notification(message)

telegram_dispatcher = TelegramDispatcher()
