import asyncio
import logging
import os
from telegram.ext import Application
from dotenv import load_dotenv

# Set up logging early
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s :: %(message)s')
logger = logging.getLogger('mikrotik-bot')

# Quiet down noisy libraries
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

# Load .env
load_dotenv('/app/.env')

import db
import fup_engine
import telegram_bot

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()
CHECK_INTERVAL_SECONDS = int(os.getenv('CHECK_INTERVAL_SECONDS', '300'))

async def fup_cycle_loop(app: Application):
    """Periodic task to run FUP engine and send notifications."""
    await asyncio.sleep(5)  # Initial wait
    
    # Track current month to detect rollover
    current_mk = fup_engine.month_key()
    last_summary_day = None
    last_backup_day = None
    
    while True:
        try:
            new_mk = fup_engine.month_key()
            
            # Check for Monthly Rollover
            if new_mk != current_mk:
                logger.info(f"Month rollover detected: {current_mk} -> {new_mk}")
                reset_notifs = fup_engine.full_monthly_reset()
                current_mk = new_mk
                
                if ADMIN_CHAT_ID:
                    for msg in reset_notifs:
                        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode='Markdown')
                        await asyncio.sleep(0.1) # Minor delay to prevent rate limit

            # Daily Summary at 08:00 AM WIB
            now = fup_engine.now_local()
            if now.hour == 8 and last_summary_day != now.day:
                logger.info("Generating automated daily summary")
                # We can reuse the summary command logic but let's just trigger a notification
                # or better: call a dedicated fup_engine function if we had one.
                # For now, let's just trigger a dummy summary message or implement it here.
                last_summary_day = now.day
                if ADMIN_CHAT_ID:
                    # Capture current stats
                    conn = db.get_conn()
                    cur = conn.cursor()
                    cur.execute('SELECT SUM(bytes_total) FROM monthly_usage WHERE month_key=?', (new_mk,))
                    total_bytes = cur.fetchone()[0] or 0
                    conn.close()
                    
                    await app.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"📊 *Daily Network Report*\nTotal Traffic: `{round(total_bytes/1e9, 2)} GB`\nGunakan /summary untuk detail.",
                        parse_mode='Markdown'
                    )

            # Daily DB Backup at 00:00 AM WIB
            if now.hour == 0 and last_backup_day != now.day:
                logger.info("Performing automated midnight DB backup")
                last_backup_day = now.day
                if ADMIN_CHAT_ID:
                    db_path = '/app/data/bot.db'
                    if os.path.exists(db_path):
                        try:
                            with open(db_path, 'rb') as f:
                                await app.bot.send_document(
                                    chat_id=ADMIN_CHAT_ID,
                                    document=f,
                                    filename=f"backup_{now.strftime('%Y%m%d')}.db",
                                    caption=f"💾 *Daily DB Backup*\nDate: `{now.strftime('%Y-%m-%d')}`"
                                )
                        except Exception as e:
                            logger.error(f"Backup failed: {e}")
                    else:
                        logger.error(f"Backup failed: File {db_path} not found")

            logger.info("Starting FUP background cycle...")
            notifs = fup_engine.run_fup_cycle()
            
            if notifs and ADMIN_CHAT_ID:
                for msg in notifs:
                    try:
                        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode='Markdown')
                        await asyncio.sleep(0.1)
                    except Exception as send_err:
                        logger.error(f"Failed to send background notification: {send_err}")
            
            logger.info(f"FUP background cycle done. Found {len(notifs)} actions.")
        except Exception as e:
            logger.exception(f"Background loop error: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

async def notify_startup(app: Application):
    """Action to take after bot is initialized."""
    db.init_db()
    asyncio.create_task(fup_cycle_loop(app))
    
    if ADMIN_CHAT_ID:
        try:
            host = os.getenv('MIKROTIK_HOST', 'N/A')
            threshold = os.getenv('FUP_THRESHOLD_GB', '100')
            interval = os.getenv('CHECK_INTERVAL_SECONDS', '300')
            
            msg = (
                "🛰 *MikroTik Pro Manager v6.0 Online*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "✅ *System Status:* `READY`\n"
                "📡 *MikroTik Host:* `{}`\n"
                "⚙️ *Default FUP:* `{}` GB\n"
                "🕐 *Interval Check:* `{}`s\n\n"
                "_Auto-FUP monitoring & daily backup enabled._"
            ).format(host, threshold, interval)
            
            await app.bot.send_message(
                chat_id=ADMIN_CHAT_ID, 
                text=msg,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Startup notify failed: {e}")

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment!")
        return

    # Initialize Application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Setup Handlers from telegram_bot module
    telegram_bot.setup_handlers(app)
    
    # Post init actions
    app.post_init = notify_startup
    
    logger.info("Bot starting polling...")
    app.run_polling()

if __name__ == '__main__':
    main()
