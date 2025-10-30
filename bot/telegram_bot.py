"""
Telegram Bot handler for /status and /stats commands
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
        logger.info("🔧 [TelegramBotHandler] Initialized")
    
    async def start_bot(self):
        try:
            logger.info("🚀 [TelegramBotHandler] Starting Telegram bot...")
            
            # In v20.x, use Application instead of Updater
            self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
            
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            
            # Start polling in background task (v20.x is async)
            asyncio.create_task(self.application.run_polling())
            
            logger.info("✅ [TelegramBotHandler] Telegram bot started successfully")
            
        except Exception as e:
            logger.error(f"❌ [TelegramBotHandler] Error starting bot: {e}")
            raise
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            logger.info(f"📥 [TelegramBotHandler] Received /status command from user {update.effective_user.id}")
            
            # Get symbol count from cache (non-blocking)
            active_symbols = redis_manager.get('active_symbols')
            symbol_count = len(active_symbols) if active_symbols else 0
            
            # Get open signals count with timeout protection
            open_signals = 0
            try:
                with db_manager.get_session() as session:
                    open_signals = session.query(Signal).filter(
                        Signal.status == 'OPEN'
                    ).count()
            except Exception as db_error:
                logger.warning(f"⚠️ [TelegramBotHandler] DB query failed in status command: {db_error}")
                open_signals = 0  # Fallback to 0 if DB unavailable
            
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
            
            # Get stats with error protection
            stats = None
            try:
                stats = performance_monitor.get_stats_for_telegram()
            except Exception as stats_error:
                logger.warning(f"⚠️ [TelegramBotHandler] Failed to get stats: {stats_error}")
            
            if not stats:
                update.message.reply_text("No statistics available yet")
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
    
    async def stop_bot(self):
        if self.application:
            await self.application.stop()
            logger.info("🛑 [TelegramBotHandler] Telegram bot stopped")

telegram_bot_handler = TelegramBotHandler()
