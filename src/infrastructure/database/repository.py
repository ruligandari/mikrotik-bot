import sqlite3
import logging
from typing import List, Optional, Tuple
from src.config import Config
from src.domain.models import User, Usage, UserState, ActionLog

logger = logging.getLogger('mikrotik-bot.infrastructure.database')

class SqliteRepository:
    def __init__(self):
        self.db_path = Config.DB_PATH

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        conn = self.get_conn()
        cur = conn.cursor()
        
        # User Configuration & Data
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                pppoe_name TEXT,
                queue_name TEXT,
                profile TEXT,
                whatsapp TEXT,
                enabled INTEGER DEFAULT 1,
                threshold_gb REAL DEFAULT NULL,
                updated_at TEXT
            )
        ''')

        # Monthly Usage Stats
        cur.execute('''
            CREATE TABLE IF NOT EXISTS monthly_usage (
                month_key TEXT,
                username TEXT,
                bytes_in INTEGER DEFAULT 0,
                bytes_out INTEGER DEFAULT 0,
                bytes_total INTEGER DEFAULT 0,
                last_raw_total INTEGER DEFAULT 0,
                last_sample_at TEXT,
                PRIMARY KEY (month_key, username)
            )
        ''')

        # FUP State Management
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_state (
                username TEXT PRIMARY KEY,
                month_key TEXT,
                state TEXT DEFAULT 'normal',
                last_action_at TEXT,
                last_reason TEXT
            )
        ''')

        # Subscriptions / Billing Status
        cur.execute('''
            CREATE TABLE IF NOT EXISTS billing_status (
                username TEXT,
                month_key TEXT,
                is_paid INTEGER DEFAULT 0,
                amount_paid REAL DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (username, month_key)
            )
        ''')

        # Payment History
        cur.execute('''
            CREATE TABLE IF NOT EXISTS payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                username TEXT,
                month_key TEXT,
                amount REAL,
                method TEXT DEFAULT 'manual'
            )
        ''')

        conn.commit()
        
        # Action Logging
        cur.execute('''
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                username TEXT,
                action TEXT,
                detail TEXT
            )
        ''')
        
        conn.commit()
        
        # System Settings
        cur.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()
        
        # Migrations
        self._migrate(cur, conn)
        conn.close()

    def _migrate(self, cur, conn):
        # last_raw_total migration
        try:
            cur.execute('SELECT last_raw_total FROM monthly_usage LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("SqliteRepository: Adding last_raw_total to monthly_usage")
            cur.execute('ALTER TABLE monthly_usage ADD COLUMN last_raw_total INTEGER DEFAULT 0')
            conn.commit()

        # threshold_gb migration
        try:
            cur.execute('SELECT threshold_gb FROM users LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("SqliteRepository: Adding threshold_gb to users")
            cur.execute('ALTER TABLE users ADD COLUMN threshold_gb REAL DEFAULT NULL')
            conn.commit()

        # profile migration
        try:
            cur.execute('SELECT profile FROM users LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("SqliteRepository: Adding profile to users")
            cur.execute('ALTER TABLE users ADD COLUMN profile TEXT')
            conn.commit()

        # whatsapp migration
        try:
            cur.execute('SELECT whatsapp FROM users LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("SqliteRepository: Adding whatsapp to users")
            cur.execute('ALTER TABLE users ADD COLUMN whatsapp TEXT')
            conn.commit()

    def update_usage_bulk(self, rows: list):
        """
        rows: List of (uname, qname, bi, bo, bt, ts, mk)
        """
        conn = self.get_conn()
        cur = conn.cursor()
        for uname, qname, bi, bo, bt, ts, mk in rows:
            # 1. Update users dictionary
            cur.execute('''
                INSERT INTO users(username, pppoe_name, queue_name, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    pppoe_name=excluded.pppoe_name,
                    queue_name=excluded.queue_name,
                    updated_at=excluded.updated_at
            ''', (uname, uname, qname, ts))

            # 2. Accumulate Usage
            cur.execute('SELECT bytes_total, last_raw_total FROM monthly_usage WHERE month_key=? AND username=?', (mk, uname))
            prev = cur.fetchone()
            
            if prev:
                old_total, old_raw = prev
                delta = (bt - old_raw) if bt >= old_raw else bt
                new_total = old_total + delta
            else:
                new_total = 0 # Baseline reset for the first sample of a month
                
            cur.execute('''
                INSERT INTO monthly_usage(month_key, username, bytes_in, bytes_out, bytes_total, last_raw_total, last_sample_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(month_key, username) DO UPDATE SET
                    bytes_in=excluded.bytes_in,
                    bytes_out=excluded.bytes_out,
                    bytes_total=excluded.bytes_total,
                    last_raw_total=excluded.last_raw_total,
                    last_sample_at=excluded.last_sample_at
            ''', (mk, uname, bi, bo, new_total, bt, ts))
            
        conn.commit()
        conn.close()

    def get_accumulated_bytes(self, month_key: str, username: str) -> int:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT bytes_total FROM monthly_usage WHERE month_key=? AND username=?', (month_key, username))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0

    def get_user_config(self, username: str) -> Tuple[bool, float]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT enabled, threshold_gb FROM users WHERE username=?', (username,))
        row = cur.fetchone()
        conn.close()
        if row:
            enabled, thresh = row
            return bool(enabled), (thresh if thresh is not None else Config.FUP_THRESHOLD_GB)
        return True, Config.FUP_THRESHOLD_GB

    def get_user_profile(self, username: str) -> str:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT profile FROM users WHERE username=?', (username,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else 'NORMAL'

    def set_user_whatsapp(self, username: str, number: Optional[str]):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('UPDATE users SET whatsapp=? WHERE username=?', (number, username))
        conn.commit()
        conn.close()

    # --- Settings Handlers ---
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT value FROM settings WHERE key=?', (key,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()
        conn.close()
        return value

    def get_user_whatsapp(self, username: str) -> Optional[str]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT whatsapp FROM users WHERE username=?', (username,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def set_user_config(self, username: str, enabled: Optional[bool] = None, threshold: Optional[float] = None):
        conn = self.get_conn()
        cur = conn.cursor()
        if enabled is not None:
            cur.execute('UPDATE users SET enabled=? WHERE username=?', (1 if enabled else 0, username))
        if threshold is not None:
            cur.execute('UPDATE users SET threshold_gb=? WHERE username=?', (threshold, username))
        conn.commit()
        conn.close()

    def register_user(self, username: str, pppoe_name: str, queue_name: str, profile: str = 'NORMAL', whatsapp: str = None):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO users(username, pppoe_name, queue_name, profile, whatsapp, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                pppoe_name=excluded.pppoe_name,
                queue_name=excluded.queue_name,
                profile=excluded.profile,
                whatsapp=COALESCE(excluded.whatsapp, users.whatsapp),
                updated_at=excluded.updated_at
        ''', (username, pppoe_name, queue_name, profile, whatsapp, Config.now_local().isoformat()))
        conn.commit()
        conn.close()

    def get_user_state(self, username: str) -> Optional[UserState]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT state, month_key, last_action_at, last_reason FROM user_state WHERE username=?', (username,))
        row = cur.fetchone()
        conn.close()
        if row:
            return UserState(username=username, state=row[0], month_key=row[1], last_action_at=row[2], last_reason=row[3])
        return None

    def save_user_state(self, state: UserState):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO user_state(username, month_key, state, last_action_at, last_reason)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                month_key=excluded.month_key,
                state=excluded.state,
                last_action_at=excluded.last_action_at,
                last_reason=excluded.last_reason
        ''', (state.username, state.month_key, state.state, state.last_action_at, state.last_reason))
        conn.commit()
        conn.close()

    def log_action(self, log: ActionLog):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('INSERT INTO action_log(ts, username, action, detail) VALUES(?, ?, ?, ?)',
                    (log.ts, log.username, log.action, log.detail))
        conn.commit()
        conn.close()

    def get_all_users_config(self) -> List[Tuple[str, bool, Optional[float], str, str]]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT username, enabled, threshold_gb, profile, whatsapp FROM users')
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_top_usage(self, month_key: str, limit: int = 10) -> List[Tuple[str, int]]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('''
            SELECT username, bytes_total
            FROM monthly_usage
            WHERE month_key=?
            ORDER BY bytes_total DESC
            LIMIT ?
        ''', (month_key, limit))
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_total_network_usage(self, month_key: str) -> int:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT SUM(bytes_total) FROM monthly_usage WHERE month_key=?', (month_key,))
        row = cur.fetchone()
        conn.close()
        return row[0] or 0

    def get_throttled_users(self, month_key: str) -> List[Tuple[str, str, str]]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('''
            SELECT username, last_action_at, last_reason
            FROM user_state
            WHERE state='throttled' AND month_key=?
        ''', (month_key,))
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_action_logs(self, username: str, limit: int = 10) -> List[Tuple[str, str, str]]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT ts, action, detail FROM action_log WHERE username=? ORDER BY ts DESC LIMIT ?', (username, limit))
        rows = cur.fetchall()
        conn.close()
        return rows

    # --- Billing Methods ---

    def get_billing_status(self, username: str, month_key: str) -> Optional[Tuple[bool, float, str]]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT is_paid, amount_paid, updated_at FROM billing_status WHERE username=? AND month_key=?', (username, month_key))
        row = cur.fetchone()
        conn.close()
        if row:
            return bool(row[0]), row[1], row[2]
        return None

    def mark_as_paid(self, username: str, month_key: str, amount: float):
        ts = Config.now_local().isoformat()
        conn = self.get_conn()
        cur = conn.cursor()
        # 1. Update status
        cur.execute('''
            INSERT INTO billing_status(username, month_key, is_paid, amount_paid, updated_at)
            VALUES(?, ?, 1, ?, ?)
            ON CONFLICT(username, month_key) DO UPDATE SET
                is_paid=1, amount_paid=amount_paid + excluded.amount_paid, updated_at=excluded.updated_at
        ''', (username, month_key, amount, ts))
        
        # 2. Log history
        cur.execute('INSERT INTO payment_history(ts, username, month_key, amount, method) VALUES(?, ?, ?, ?, ?)',
                    (ts, username, month_key, amount, 'manual'))
        
        conn.commit()
        conn.close()

    def get_unpaid_users(self, month_key: str) -> List[str]:
        """Returns list of usernames who have NOT paid for the given month but are monitored."""
        conn = self.get_conn()
        cur = conn.cursor()
        # Check users who exist in 'users' table but not in 'billing_status' (as paid)
        cur.execute('''
            SELECT u.username 
            FROM users u
            LEFT JOIN billing_status b ON u.username = b.username AND b.month_key = ?
            WHERE u.enabled = 1 AND (b.is_paid IS NULL OR b.is_paid = 0)
        ''', (month_key,))
        rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_unpaid_with_profile(self, month_key: str) -> List[Tuple[str, str]]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute('''
            SELECT u.username, u.profile
            FROM users u
            LEFT JOIN billing_status b ON u.username = b.username AND b.month_key = ?
            WHERE u.enabled = 1 AND (b.is_paid IS NULL OR b.is_paid = 0)
        ''', (month_key,))
        rows = cur.fetchall()
        conn.close()
        return rows
