#!/usr/bin/env python3
"""
Test script for telegram bot v20.x background polling
"""
import asyncio
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is running!")
    print(f"Received /status from {update.effective_user.id}")

async def test_background_polling():
    """Test the same pattern as in bot/telegram_bot.py"""
    print("🚀 Testing telegram bot background polling...")
    
    # Build application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("status", status_command))
    
    # Try Method 1: initialize + start + start_polling (current code)
    print("\n📋 Method 1: await updater.start_polling()")
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        print("✅ Method 1 SUCCESS - Bot started!")
        
        # Keep running for 10 seconds
        print("⏳ Running for 10 seconds, send /status to test...")
        await asyncio.sleep(10)
        
        # Stop
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        print("🛑 Bot stopped cleanly")
        
    except Exception as e:
        print(f"❌ Method 1 FAILED: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()

async def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in environment")
        return
    
    print(f"✅ Token found: {TELEGRAM_BOT_TOKEN[:10]}...")
    
    await test_background_polling()

if __name__ == '__main__':
    asyncio.run(main())
