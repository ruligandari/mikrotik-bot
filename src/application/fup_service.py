import logging
from src.config import Config
from src.domain.models import ActionLog, UserState
from src.infrastructure.mikrotik.gateway import MikrotikGateway
from src.infrastructure.database.repository import SqliteRepository

logger = logging.getLogger('mikrotik-bot.application.fup_service')

class FupService:
    def __init__(self, repo: SqliteRepository, mk_gateway: MikrotikGateway):
        self.repo = repo
        self.mk_gateway = mk_gateway

    def run_fup_cycle(self):
        """Orchestrates the FUP check cycle."""
        mk = Config.month_key()
        ts = Config.now_local().isoformat()
        notifications = []

        try:
            usage_data = self.mk_gateway.fetch_usage()
            if not usage_data:
                return []
        except Exception as e:
            logger.error(f"FupService: Failed to fetch usage: {e}")
            return [f"❌ FUP Cycle Gagal: Gagal fetch usage dari MikroTik: {e}"]

        # Update DB in bulk
        db_rows = []
        for u in usage_data:
            db_rows.append((u['username'], u['queue_name'], u['bytes_in'], u['bytes_out'], u['bytes_total'], ts, mk))
        
        self.repo.update_usage_bulk(db_rows)
        logger.info(f"FupService: Updated usage for {len(db_rows)} users in DB")

        # Threshold check
        for u in usage_data:
            uname = u['username']
            enabled, user_threshold_gb = self.repo.get_user_config(uname)
            if not enabled:
                continue

            bt = self.repo.get_accumulated_bytes(mk, uname)
            bt_gb = Config.to_gb(bt)
            limit_bytes = int(user_threshold_gb * 1_000_000_000)
            
            user_state_obj = self.repo.get_user_state(uname)
            current_state = user_state_obj.state if user_state_obj else 'normal'
            current_mk = user_state_obj.month_key if user_state_obj else mk

            # Scenario 1: Needs throttling
            if bt >= limit_bytes:
                if current_state != 'throttled' or current_mk != mk:
                    logger.info(f"FupService: Throttling {uname} via Profile {Config.THROTTLE_RATE}")
                    success, err = self.mk_gateway.set_pppoe_profile(uname, Config.THROTTLE_RATE)
                    if success:
                        self.mk_gateway.disconnect_pppoe_user(uname)
                        new_state = UserState(uname, mk, 'throttled', ts, f"Usage {bt_gb} GB >= {user_threshold_gb} GB")
                        self.repo.save_user_state(new_state)
                        self.repo.log_action(ActionLog(ts=ts, username=uname, action='THROTTLE', detail=new_state.last_reason))
                        notifications.append(
                            f"⚠️ *FUP Alert: {uname}*\nUsage: `{bt_gb} GB` >= `{user_threshold_gb} GB`.\nProfile: `{Config.THROTTLE_RATE}`"
                        )
                    else:
                        notifications.append(f"❌ Gagal throttle `{uname}`: {err}")

            # Scenario 1B: Warning notifications (80%, 90%)
            elif current_state != 'throttled' or current_mk != mk:
                pct = (bt / limit_bytes) * 100
                if 80 <= pct < 80.5: # Slightly wider to avoid missing some close ticks
                    notifications.append(f"📢 *FUP Warning: {uname}*\nPemakaian sudah mencapai `80%` ({bt_gb} GB / {user_threshold_gb} GB)")
                elif 90 <= pct < 90.5:
                    notifications.append(f"📢 *FUP Warning: {uname}*\nPemakaian sudah mencapai `90%` ({bt_gb} GB / {user_threshold_gb} GB)")

            # Scenario 2: Monthly reset
            elif current_state == 'throttled' and current_mk != mk:
                logger.info(f"FupService: Resetting {uname} to normal profile (Bulan baru)")
                success, err = self.mk_gateway.set_pppoe_profile(uname, Config.BASE_RATE)
                if success:
                    self.mk_gateway.disconnect_pppoe_user(uname)
                    self.repo.save_user_state(UserState(uname, mk, 'normal', ts, "Monthly reset"))
                    self.repo.log_action(ActionLog(ts=ts, username=uname, action='UNTHROTTLE', detail=f"Reset to {Config.BASE_RATE} for {mk}"))
                    notifications.append(f"✅ *FUP Reset: {uname}*\nBulan baru `{mk}`. Profile dikembalikan ke `{Config.BASE_RATE}`.")
                else:
                    notifications.append(f"❌ Gagal reset `{uname}`: {err}")
            
            # Scenario 3: Initial state for the month
            elif user_state_obj is None or current_mk != mk:
                self.repo.save_user_state(UserState(uname, mk, 'normal', ts, "Initial check for month"))

        return notifications

    def full_monthly_reset(self):
        """Force reset all users at the start of the month."""
        mk = Config.month_key()
        ts = Config.now_local().isoformat()
        logger.info(f"FupService: Proactive monthly reset for {mk}")
        notifications = [f"📅 *Monthly Reset: {mk}*\nMengembalikan semua user ke speed normal..."]
        
        try:
            usage_data = self.mk_gateway.fetch_usage()
        except:
            return [f"❌ Reset gagal: Gagal akses MikroTik"]

        q_map = {u['username']: u['queue_name'] for u in usage_data}
        reset_count = 0
        
        # Get all users who have state in DB
        all_configs = self.repo.get_all_users_config()
        for uname, _, _, _ in all_configs:
            success, err = self.mk_gateway.set_pppoe_profile(uname, Config.BASE_RATE)
            if success:
                self.mk_gateway.disconnect_pppoe_user(uname)
                self.repo.save_user_state(UserState(uname, mk, 'normal', ts, "Proactive monthly reset"))
                self.repo.log_action(ActionLog(ts=ts, username=uname, action='UNTHROTTLE', detail=f"Reset to {Config.BASE_RATE} (Monthly)"))
                reset_count += 1
                
        notifications.append(f"✅ Reset selesai. `{reset_count}` user dikembalikan ke `{Config.BASE_RATE}`.")
        return notifications
