import logging
from src.config import Config
from src.domain.models import ActionLog
from src.infrastructure.mikrotik.gateway import MikrotikGateway
from src.infrastructure.database.repository import SqliteRepository

logger = logging.getLogger('mikrotik-bot.application.admin_service')

class AdminService:
    def __init__(self, repo: SqliteRepository, mk_gateway: MikrotikGateway):
        self.repo = repo
        self.mk_gateway = mk_gateway

    def fetch_active_sessions(self):
        return self.mk_gateway.fetch_active_sessions()

    def get_ppp_profiles(self):
        return self.mk_gateway.fetch_ppp_profiles()

    def add_user(self, username, password, profile):
        new_ip = self.mk_gateway.get_next_pppoe_ip()
        success, err = self.mk_gateway.add_ppp_secret(username, password, profile, new_ip)
        if success:
            ts = Config.now_local().isoformat()
            # Register immediately so they appear in /users with their profile
            self.repo.register_user(username, username, f"<pppoe-{username}>", profile)
            self.repo.log_action(ActionLog(ts=ts, username=username, action='ADD_USER', detail=f"Profile: {profile}, IP: {new_ip}"))
            return True, new_ip, ""
        return False, None, err

    def delete_user(self, username):
        success, err = self.mk_gateway.remove_ppp_secret(username)
        if success:
            ts = Config.now_local().isoformat()
            # Also remove from DB to keep /users list clean
            conn = self.repo.get_conn()
            cur = conn.cursor()
            cur.execute('DELETE FROM users WHERE username=?', (username,))
            conn.commit()
            conn.close()
            
            self.repo.log_action(ActionLog(ts=ts, username=username, action='DEL_USER', detail="Secret removed from MikroTik and Database"))
            return True, ""
        return False, err

    def kick_user(self, username):
        success, err = self.mk_gateway.disconnect_pppoe_user(username)
        if success:
            ts = Config.now_local().isoformat()
            self.repo.log_action(ActionLog(ts=ts, username=username, action='KICK', detail="Active session kicked manually"))
            return True, ""
        return False, err

    def update_user_limit(self, username, limit_gb):
        self.repo.set_user_config(username, threshold=limit_gb)
        ts = Config.now_local().isoformat()
        self.repo.log_action(ActionLog(ts=ts, username=username, action='SET_LIMIT', detail=f"New limit: {limit_gb} GB"))

    def toggle_user_fup(self, username, enabled: bool):
        self.repo.set_user_config(username, enabled=enabled)
        ts = Config.now_local().isoformat()
        self.repo.log_action(ActionLog(ts=ts, username=username, action='SET_ENABLED', detail=f"Enabled: {enabled}"))
        
    def get_summary_data(self):
        mk = Config.month_key()
        total_usage = self.repo.get_total_network_usage(mk)
        top_users = self.repo.get_top_usage(mk, limit=5)
        return total_usage, top_users
