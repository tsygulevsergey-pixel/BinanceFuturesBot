"""
Telegram Bot handler for /status, /stats, and /alltime commands
Provides real-time status and detailed statistics
"""
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from bot.config import Config
from bot.utils import logger
from bot.utils.redis_manager import redis_manager
from bot.modules import performance_monitor
from bot.database import db_manager, Signal

class TelegramBotHandler:
    def __init__(self):
        self.application = None
        self._polling_task = None
        logger.info("🔧 [TelegramBotHandler] Initialized")
    
    async def start_bot(self):
        try:
            logger.info("🚀 [TelegramBotHandler] Starting Telegram bot...")
            
            # In v20.x, use Application instead of Updater
            self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
            
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("alltime", self.alltime_command))
            
            # Proper way to start polling in background for v20.x
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            logger.info("✅ [TelegramBotHandler] Telegram bot started successfully with proxy")
            
        except Exception as e:
            logger.error(f"❌ [TelegramBotHandler] Error starting bot: {e}")
            raise
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            logger.info(f"📥 [TelegramBotHandler] Received /status command from user {update.effective_user.id}")
            
            # Get symbol count from cache (run in thread to avoid blocking event loop)
            def get_symbol_count():
                active_symbols = redis_manager.get('active_symbols')
                return len(active_symbols) if active_symbols else 0
            
            symbol_count = await asyncio.to_thread(get_symbol_count)
            
            # Get open signals count (run in thread to avoid blocking event loop)
            def get_open_signals():
                try:
                    with db_manager.get_session() as session:
                        return session.query(Signal).filter(Signal.status == 'OPEN').count()
                except Exception as db_error:
                    logger.warning(f"⚠️ [TelegramBotHandler] DB query failed: {db_error}")
                    return 0
            
            open_signals = await asyncio.to_thread(get_open_signals)
            
            message = f"""
📊 **Bot Status**

✅ **Status:** Running 24/7
🔍 **Analyzing:** {symbol_count} symbols

📈 **Open Signals:** {open_signals}

⏰ **Uptime:** Active
"""
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
            logger.info(f"📤 [TelegramBotHandler] Sent status response: {symbol_count} symbols, {open_signals} open signals")
            
        except Exception as e:
            logger.error(f"❌ [TelegramBotHandler] Error in status command: {e}", exc_info=True)
            await update.message.reply_text("Error retrieving status")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            logger.info(f"📥 [TelegramBotHandler] Received /stats command from user {update.effective_user.id}")
            
            # Get stats (run in thread to avoid blocking event loop)
            def get_stats():
                try:
                    return performance_monitor.get_stats_for_telegram()
                except Exception as stats_error:
                    logger.warning(f"⚠️ [TelegramBotHandler] Failed to get stats: {stats_error}")
                    return None
            
            stats = await asyncio.to_thread(get_stats)
            
            if not stats:
                await update.message.reply_text("No statistics available yet")
                return
            
            message = f"""
📊 **Detailed Statistics (Today)**

🎯 **Signals Generated:** {stats.get('total_signals', 0)}
🔥 **HIGH Priority:** {stats.get('high_priority', 0)}
⚡ **MEDIUM Priority:** {stats.get('medium_priority', 0)}
💡 **LOW Priority:** {stats.get('low_priority', 0)}

✅ **Win Rate:** {stats.get('win_rate', 0):.1f}%
💰 **Total PnL:** {stats.get('total_pnl', 0):+.2f}%

🎯 **TP1 Hit:** {stats.get('tp1_count', 0)} times
🎯 **TP2 Hit:** {stats.get('tp2_count', 0)} times
🛑 **SL Hit:** {stats.get('sl_count', 0)} times
"""
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
            logger.info(f"📤 [TelegramBotHandler] Sent stats response")
            
        except Exception as e:
            logger.error(f"❌ [TelegramBotHandler] Error in stats command: {e}", exc_info=True)
            await update.message.reply_text("Error retrieving statistics")
    
    async def alltime_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            logger.info(f"📥 [TelegramBotHandler] Received /alltime command from user {update.effective_user.id}")
            
            # Get all-time stats (run in thread to avoid blocking event loop)
            def get_alltime_stats():
                try:
                    return performance_monitor.get_alltime_stats_for_telegram()
                except Exception as stats_error:
                    logger.warning(f"⚠️ [TelegramBotHandler] Failed to get alltime stats: {stats_error}")
                    return None
            
            stats = await asyncio.to_thread(get_alltime_stats)
            
            if not stats:
                await update.message.reply_text("No statistics available yet")
                return
            
            # Calculate days since first signal
            from datetime import datetime
            first_date = stats.get('first_date')
            days_running = (datetime.now().date() - first_date).days if first_date else 0
            
            message = f"""
📊 **ALL TIME Statistics**

📅 **Period:** {first_date} - Today ({days_running} days)

🎯 **Total Signals:** {stats.get('total_signals', 0)}
🔥 **HIGH Priority:** {stats.get('high_priority', 0)}
⚡ **MEDIUM Priority:** {stats.get('medium_priority', 0)}
💡 **LOW Priority:** {stats.get('low_priority', 0)}

📈 **Total Trades:** {stats.get('total_trades', 0)}
✅ **Wins:** {stats.get('win_count', 0)}
❌ **Losses:** {stats.get('loss_count', 0)}
🎲 **Win Rate:** {stats.get('win_rate', 0):.1f}%

💰 **Total PnL:** {stats.get('total_pnl', 0):+.2f}%
📊 **Average PnL:** {stats.get('avg_pnl', 0):+.2f}%
⏱️ **Avg Hold Time:** {stats.get('avg_hold_time', 0):.0f} min

🎯 **TP1 Hit:** {stats.get('tp1_count', 0)} times
🎯 **TP2 Hit:** {stats.get('tp2_count', 0)} times
🛑 **SL Hit:** {stats.get('sl_count', 0)} times
"""
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
            logger.info(f"📤 [TelegramBotHandler] Sent alltime stats response")
            
        except Exception as e:
            logger.error(f"❌ [TelegramBotHandler] Error in alltime command: {e}", exc_info=True)
            await update.message.reply_text("Error retrieving all-time statistics")
    
    async def stop_bot(self):
        if self.application:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("🛑 [TelegramBotHandler] Telegram bot stopped")
            except Exception as e:
                logger.error(f"❌ [TelegramBotHandler] Error stopping bot: {e}")

telegram_bot_handler = TelegramBotHandler()
