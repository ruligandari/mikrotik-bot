import logging
from src.config import Config
from src.domain.models import ActionLog
from src.infrastructure.mikrotik.gateway import MikrotikGateway
from src.infrastructure.database.repository import SqliteRepository

logger = logging.getLogger('mikrotik-bot.application.billing_service')

class BillingService:
    def __init__(self, repo: SqliteRepository, mk_gateway: MikrotikGateway):
        self.repo = repo
        self.mk_gateway = mk_gateway

    def process_payment(self, username: str, amount: float):
        mk = Config.month_key()
        # 1. Save to DB
        self.repo.mark_as_paid(username, mk, amount)
        
        # 2. Check if currently isolated and re-enable if needed
        # Isolation logic: disabling secret
        is_disabled, _ = self.mk_gateway.get_pppoe_secret_status(username)
        if is_disabled:
            success, err = self.mk_gateway.enable_pppoe_secret(username)
            if success:
                ts = Config.now_local().isoformat()
                self.repo.log_action(ActionLog(ts=ts, username=username, action='RE-ENABLE', detail="Internet re-enabled after payment"))
                return True, "Payment recorded and internet re-enabled."
            return True, f"Payment recorded but failed to re-enable internet: {err}"
            
        return True, "Payment recorded successfully."

    def run_billing_enforcement(self) -> list:
        """
        Executes isolation for unpaid users if today > 20th.
        Returns list of notification messages.
        """
        now = Config.now_local()
        mk = Config.month_key()
        notifs = []

        if now.day <= Config.BILLING_DUE_DAY:
            logger.info(f"BillingService: Before due day ({Config.BILLING_DUE_DAY}), skipping enforcement.")
            return notifs

        unpaid_data = self.repo.get_unpaid_with_profile(mk)
        if not unpaid_data:
            return notifs

        logger.info(f"BillingService: Found {len(unpaid_data)} unpaid users after due date. Isolating...")

        for username, profile in unpaid_data:
            price = Config.PACKAGES.get(profile, Config.BILLING_MONTHLY_PRICE)
            # Check if already disabled to avoid redundant actions
            is_disabled, _ = self.mk_gateway.get_pppoe_secret_status(username)
            if not is_disabled:
                success, err = self.mk_gateway.disable_pppoe_secret(username)
                if success:
                    # Disconnect active session to enforce immediate isolation
                    self.mk_gateway.disconnect_pppoe_user(username)
                    
                    ts = Config.now_local().isoformat()
                    self.repo.log_action(ActionLog(ts=ts, username=username, action='ISOLIR', detail=f"Disabled due to unpaid bill for {mk} ({profile} - Rp {price:,.0f})"))
                    notifs.append(f"⛔ *Isolir Otomatis:* `{username}`\n  ├ Paket: `{profile}`\n  ├ Tagihan: `Rp {price:,.0f}`\n  └ Status: *DINONAKTIFKAN*")
                else:
                    logger.error(f"Failed to isolate {username}: {err}")

        return notifs

    def get_unpaid_report(self):
        mk = Config.month_key()
        unpaid = self.repo.get_unpaid_users(mk)
        return unpaid
