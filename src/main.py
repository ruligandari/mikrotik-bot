import asyncio
import logging
import sys
import uvicorn
from telegram.ext import Application
from src.config import Config
from src.infrastructure.database.repository import SqliteRepository
from src.infrastructure.mikrotik.gateway import MikrotikGateway
from src.application.fup_service import FupService
from src.application.admin_service import AdminService
from src.application.billing_service import BillingService
from src.interface.telegram.bot import TelegramBotInterface
from src.interface.worker.background import BackgroundWorker
from src.interface.api.app import create_app

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s :: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('mikrotik-bot')
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

async def run_bot_and_api():
    # Dependency Injection Container
    repo = SqliteRepository()
    mk_gateway = MikrotikGateway()
    repo.init_db()
    
    fup_service = FupService(repo, mk_gateway)
    admin_service = AdminService(repo, mk_gateway)
    billing_service = BillingService(repo, mk_gateway)
    
    # 1. Setup Telegram Bot
    app = Application.builder().token(Config.BOT_TOKEN).build()
    bot_interface = TelegramBotInterface(fup_service, admin_service, billing_service, repo, mk_gateway)
    bot_interface.setup_handlers(app)
    
    # 2. Setup FastAPI
    web_app = create_app(fup_service, admin_service, billing_service)
    config = uvicorn.Config(web_app, host="0.0.0.0", port=Config.API_PORT, log_level="info")
    server = uvicorn.Server(config)
    
    # 3. Setup Worker
    worker = BackgroundWorker(fup_service, billing_service, app)

    # Startup Notification
    if Config.ADMIN_CHAT_ID:
        try:
            msg = (
                "🛰 *MikroTik Pro Manager v7.1 (API Ready)*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🌐 *API Status:* `ONLINE` (Port {})\n"
                "🤖 *Bot Status:* `ONLINE`\n"
                "━━━━━━━━━━━━━━━━━━━━"
            ).format(Config.API_PORT)
            await app.initialize()
            await app.start()
            await app.bot.send_message(chat_id=Config.ADMIN_CHAT_ID, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Startup notify failed: {e}")

    # Run everything concurrently
    logger.info(f"Starting Bot & API (Port {Config.API_PORT})...")
    await asyncio.gather(
        app.updater.start_polling(),
        server.serve(),
        worker.start()
    )

def main():
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN not found!")
        return

    try:
        asyncio.run(run_bot_and_api())
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
