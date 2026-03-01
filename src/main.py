import asyncio
import logging
import sys
from telegram.ext import Application
from src.config import Config
from src.infrastructure.database.repository import SqliteRepository
from src.infrastructure.mikrotik.gateway import MikrotikGateway
from src.application.fup_service import FupService
from src.application.admin_service import AdminService
from src.interface.telegram.bot import TelegramBotInterface
from src.interface.worker.background import BackgroundWorker

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s :: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('mikrotik-bot')
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

async def post_init(app: Application):
    """Actions to run after bot is initialized."""
    # Dependency Injection Container (Manual)
    repo = SqliteRepository()
    mk_gateway = MikrotikGateway()
    
    # Initialize DB
    repo.init_db()
    
    # Application Services
    fup_service = FupService(repo, mk_gateway)
    admin_service = AdminService(repo, mk_gateway)
    
    # Background Worker
    worker = BackgroundWorker(fup_service, app)
    asyncio.create_task(worker.start())
    
    # Handlers Setup
    bot_interface = TelegramBotInterface(fup_service, admin_service, repo, mk_gateway)
    bot_interface.setup_handlers(app)

    # Startup Notification
    if Config.ADMIN_CHAT_ID:
        try:
            msg = (
                "🛰 *MikroTik Pro Manager v7.0 (Clean)*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "✅ *Architecture:* `Clean DDD Lifecycle`\n"
                "📡 *Host:* `{}`\n"
                "⚙️ *Interval:* `{}`s\n\n"
                "_System refactored & monitoring active._"
            ).format(Config.MIKROTIK_HOST, Config.CHECK_INTERVAL)
            await app.bot.send_message(chat_id=Config.ADMIN_CHAT_ID, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Startup notify failed: {e}")

def main():
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN not found!")
        return

    app = Application.builder().token(Config.BOT_TOKEN).build()
    app.post_init = post_init
    
    logger.info("Starting Clean MicroTik Bot...")
    app.run_polling()

if __name__ == '__main__':
    main()
