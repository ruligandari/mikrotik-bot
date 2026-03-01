import sqlite3
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger('mikrotik-bot.db')

DB_PATH = '/app/data/bot.db'
TZ = os.getenv('TZ', 'Asia/Jakarta')
DEFAULT_THRESHOLD = float(os.getenv('FUP_THRESHOLD_GB', '100'))

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()
    
    # Existing tables
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            pppoe_name TEXT,
            queue_name TEXT,
            enabled INTEGER DEFAULT 1,
            threshold_gb REAL DEFAULT NULL,
            updated_at TEXT
        )
    ''')
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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS raw_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sampled_at TEXT,
            month_key TEXT,
            username TEXT,
            bytes_in INTEGER,
            bytes_out INTEGER,
            bytes_total INTEGER
        )
    ''')
    
    # New tables for Phase 3
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_state (
            username TEXT PRIMARY KEY,
            month_key TEXT,
            state TEXT DEFAULT 'normal',
            last_action_at TEXT,
            last_reason TEXT
        )
    ''')
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
    
    # Schema Migration: Add last_raw_total if it doesn't exist
    try:
        cur.execute('SELECT last_raw_total FROM monthly_usage LIMIT 1')
    except sqlite3.OperationalError:
        logger.info("Migrating DB: Adding last_raw_total column to monthly_usage")
        cur.execute('ALTER TABLE monthly_usage ADD COLUMN last_raw_total INTEGER DEFAULT 0')
        conn.commit()

    # Schema Migration: Add threshold_gb if it doesn't exist
    try:
        cur.execute('SELECT threshold_gb FROM users LIMIT 1')
    except sqlite3.OperationalError:
        logger.info("Migrating DB: Adding threshold_gb column to users")
        cur.execute('ALTER TABLE users ADD COLUMN threshold_gb REAL DEFAULT NULL')
        conn.commit()

    conn.close()

def update_usage(rows):
    conn = get_conn()
    cur = conn.cursor()
    for uname, qname, bi, bo, bt, ts, mk in rows:
        # 1. Update users table
        cur.execute('''
            INSERT INTO users(username, pppoe_name, queue_name, enabled, updated_at)
            VALUES(?, ?, ?, 1, ?)
            ON CONFLICT(username) DO UPDATE SET
              pppoe_name=excluded.pppoe_name,
              queue_name=excluded.queue_name,
              updated_at=excluded.updated_at
        ''', (uname, uname, qname, ts))
        
        # 2. Get previous state for accumulation
        cur.execute('''
            SELECT bytes_total, last_raw_total FROM monthly_usage 
            WHERE month_key=? AND username=?
        ''', (mk, uname))
        prev = cur.fetchone()
        
        if prev:
            old_total, old_raw = prev
            # Calculate delta
            if bt >= old_raw:
                delta = bt - old_raw
            else:
                # Counter reset (reconnect/reboot/new month)
                delta = bt
            new_total = old_total + delta
        else:
            # First sample ever for this month_key. 
            # We treat the current raw counter as baseline (starting from 0).
            # If we don't do this, a Feb counter of 50GB will make March start at 50GB.
            new_total = 0
            
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
        
        # 3. Log raw sample
        cur.execute('''
            INSERT INTO raw_samples(sampled_at, month_key, username, bytes_in, bytes_out, bytes_total)
            VALUES(?, ?, ?, ?, ?, ?)
        ''', (ts, mk, uname, bi, bo, bt))
    conn.commit()
    conn.close()

def get_user_state(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT state, month_key FROM user_state WHERE username=?', (username,))
    row = cur.fetchone()
    conn.close()
    return row if row else (None, None)

def set_user_state(username, mk, state, reason=None):
    ts = datetime.now(ZoneInfo(TZ)).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO user_state(username, month_key, state, last_action_at, last_reason)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            month_key=excluded.month_key,
            state=excluded.state,
            last_action_at=excluded.last_action_at,
            last_reason=excluded.last_reason
    ''', (username, mk, state, ts, reason))
    conn.commit()
    conn.close()

def log_action(username, action, detail):
    ts = datetime.now(ZoneInfo(TZ)).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('INSERT INTO action_log(ts, username, action, detail) VALUES(?, ?, ?, ?)',
                (ts, username, action, detail))
    conn.commit()
    conn.close()

def get_user_config(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT enabled, threshold_gb FROM users WHERE username=?', (username,))
    row = cur.fetchone()
    conn.close()
    if row:
        enabled, threshold = row
        return enabled, (threshold if threshold is not None else DEFAULT_THRESHOLD)
    return 1, DEFAULT_THRESHOLD

def set_user_config(username, enabled=None, threshold=None):
    conn = get_conn()
    cur = conn.cursor()
    if enabled is not None:
        cur.execute('UPDATE users SET enabled=? WHERE username=?', (enabled, username))
    if threshold is not None:
        cur.execute('UPDATE users SET threshold_gb=? WHERE username=?', (threshold, username))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT username, enabled, threshold_gb FROM users')
    rows = cur.fetchall()
    conn.close()
    return rows
