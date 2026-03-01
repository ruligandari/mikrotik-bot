import asyncio
import logging
import os
from telegram.ext import Application
from src.config import Config
from src.application.fup_service import FupService
from src.application.billing_service import BillingService

logger = logging.getLogger('mikrotik-bot.interface.worker')

class BackgroundWorker:
    def __init__(self, fup_service: FupService, billing_service: BillingService, app: Application):
        self.fup_service = fup_service
        self.billing_service = billing_service
        self.app = app
        self.admin_id = Config.ADMIN_CHAT_ID

    async def start(self):
        """Main loop for background tasks."""
        await asyncio.sleep(10) # Initial wait
        
        current_mk = Config.month_key()
        last_summary_day = None
        last_backup_day = None
        
        while True:
            try:
                new_mk = Config.month_key()
                now = Config.now_local()
                
                # Monthly Rollover
                if new_mk != current_mk:
                    logger.info(f"Worker: Month rollover {current_mk} -> {new_mk}")
                    reset_notifs = self.fup_service.full_monthly_reset()
                    current_mk = new_mk
                    await self._notify(reset_notifs)

                # Daily Summary at 08:00 AM WIB
                if now.hour == 8 and last_summary_day != now.day:
                    last_summary_day = now.day
                    total_bytes = self.fup_service.repo.get_total_network_usage(new_mk)
                    total_gb = Config.to_gb(total_bytes)
                    await self._send(f"📊 *Daily Network Report*\nTotal Traffic: `{total_gb} GB`\nGunakan /summary untuk detail.")

                # Daily DB Backup at 00:00 AM WIB
                if now.hour == 0 and last_backup_day != now.day:
                    last_backup_day = now.day
                    await self._perform_backup(now)

                # Regular FUP Cycle
                logger.debug("Worker: Starting FUP cycle...")
                notifs = self.fup_service.run_fup_cycle()
                await self._notify(notifs)

                # Billing Enforcement (Isolation)
                logger.debug("Worker: Starting billing enforcement cycle...")
                billing_notifs = self.billing_service.run_billing_enforcement()
                await self._notify(billing_notifs)

            except Exception as e:
                logger.exception(f"Worker: Background loop error: {e}")
            
            await asyncio.sleep(Config.CHECK_INTERVAL)

    async def _notify(self, messages):
        if not messages or not self.admin_id:
            return
        for msg in messages:
            try:
                await self.app.bot.send_message(chat_id=self.admin_id, text=msg, parse_mode='Markdown')
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Worker: Send failed: {e}")

    async def _send(self, text):
        if self.admin_id:
            try:
                await self.app.bot.send_message(chat_id=self.admin_id, text=text, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Worker: Send failed: {e}")

    async def _perform_backup(self, now):
        if not self.admin_id: return
        db_path = Config.DB_PATH
        if os.path.exists(db_path):
            try:
                with open(db_path, 'rb') as f:
                    await self.app.bot.send_document(
                        chat_id=self.admin_id,
                        document=f,
                        filename=f"backup_{now.strftime('%Y%m%d')}.db",
                        caption=f"💾 *Daily DB Backup*\nDate: `{now.strftime('%Y-%m-%d')}`"
                    )
            except Exception as e:
                logger.error(f"Worker: Backup failed: {e}")
        else:
            logger.error(f"Worker: Backup failed (File not found)")
