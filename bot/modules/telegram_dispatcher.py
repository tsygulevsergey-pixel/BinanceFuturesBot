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
        self.bot = None
        
        logger.info(f"🔧 [TelegramDispatcher] Initialized with chat_id={self.chat_id}")
    
    async def initialize(self):
        try:
            self.bot = Bot(token=self.bot_token)
            me = await self.bot.get_me()
            logger.info(f"✅ [TelegramDispatcher] Connected as @{me.username}")
        except Exception as e:
            logger.error(f"❌ [TelegramDispatcher] Failed to initialize bot: {e}")
            raise
    
    async def send_signal(self, signal: Dict) -> Optional[int]:
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
        original_message_id: Optional[int] = None
    ) -> bool:
        try:
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
        try:
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
🎯 **TP1 Hit:** {stats.get('tp1_count', 0)}
🎯 **TP2 Hit:** {stats.get('tp2_count', 0)}
🛑 **SL Hit:** {stats.get('sl_count', 0)}
"""
        return await self.send_notification(message)

telegram_dispatcher = TelegramDispatcher()
