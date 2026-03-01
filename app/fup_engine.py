import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import db
import mikrotik_client

logger = logging.getLogger('mikrotik-bot.fup')

TZ = os.getenv('TZ', 'Asia/Jakarta')
FUP_THRESHOLD_GB = float(os.getenv('FUP_THRESHOLD_GB', '100'))
BASE_RATE = os.getenv('BASE_RATE', '5M/5M')
THROTTLE_RATE = os.getenv('THROTTLE_RATE', '2M/2M')

def now_local() -> datetime:
    return datetime.now(ZoneInfo(TZ))

def month_key() -> str:
    return now_local().strftime('%Y-%m')

def full_monthly_reset():
    """Force reset all users to normal state at the start of the month."""
    mk = month_key()
    logger.info(f"FUP Engine: Performing proactive monthly reset for {mk}")
    notifications = [f"📅 *Monthly Reset: {mk}*\nMengembalikan semua user ke speed normal..."]
    
    conn = db.get_conn()
    cur = conn.cursor()
    # Find users who were throttled or just need a state for the new month
    cur.execute("SELECT username FROM user_state WHERE month_key != ? OR state='throttled'", (mk,))
    users = [r[0] for r in cur.fetchall()]
    conn.close()
    
    # We also need to get queue names
    try:
        usage_data = mikrotik_client.fetch_usage()
        q_map = {u['username']: u['queue_name'] for u in usage_data}
    except Exception as e:
        logger.error(f"FUP Engine reset: failed to fetch usage/queues: {e}")
        return [f"❌ Reset gagal: Gagal akses MikroTik: {e}"]

    reset_count = 0
    for uname in users:
        qname = q_map.get(uname)
        # uname here is effectively the secret name as well based on users table
        
        success, err = mikrotik_client.set_pppoe_profile(uname, BASE_RATE)
        if success:
            mikrotik_client.disconnect_pppoe_user(uname)
            db.set_user_state(uname, mk, 'normal', reason="Proactive monthly reset")
            db.log_action(uname, 'UNTHROTTLE', f"Reset to profile {BASE_RATE} for {mk}")
            reset_count += 1
        else:
            logger.error(f"Failed to reset {uname}: {err}")
            
    notifications.append(f"✅ Reset selesai. `{reset_count}` user dikembalikan ke `{BASE_RATE}`.")
    return notifications

def run_fup_cycle():
    """
    1. Fetch current usage from MikroTik
    2. Update DB
    3. Check each user against FUP threshold
    4. Apply throttle if needed
    Returns list of notification messages.
    """
    ts = now_local().isoformat()
    mk = month_key()
    notifications = []
    
    try:
        usage_data = mikrotik_client.fetch_usage()
    except Exception as e:
        logger.error(f"FUP Engine: failed to fetch usage: {e}")
        return [f"❌ FUP Cycle Gagal: Gagal fetch usage dari MikroTik: {e}"]

    # Prepare data for DB update
    db_rows = []
    for u in usage_data:
        db_rows.append((
            u['username'],
            u['queue_name'],
            u['bytes_in'],
            u['bytes_out'],
            u['bytes_total'],
            ts,
            mk
        ))
    
    # Update DB with raw data (accumulation happens inside db.py)
    db.update_usage(db_rows)
    logger.info(f"FUP Engine: Updated usage for {len(db_rows)} users in DB")
    
    # Threshold check using accumulated totals from DB
    threshold_bytes = int(FUP_THRESHOLD_GB * 1_000_000_000)
    logger.info(f"FUP Engine: Checking {len(usage_data)} users against {FUP_THRESHOLD_GB} GB threshold")
    # FUP_THRESHOLD_GB is now a fallback/default, actual threshold is per-user
    logger.info(f"FUP Engine: Checking {len(usage_data)} users against their configured thresholds")
    
    conn = db.get_conn()
    cur = conn.cursor()
    
    for u in usage_data:
        uname = u['username']
        # Fetch per-user config
        enabled, user_threshold_gb = db.get_user_config(uname)
        
        if not enabled:
            logger.info(f"FUP Engine: Skip user {uname} because disabled")
            continue

        # Fetch the accumulated total we just updated
        cur.execute('SELECT bytes_total FROM monthly_usage WHERE month_key=? AND username=?', (mk, uname))
        row = cur.fetchone()
        bt = row[0] if row else u['bytes_total']
        bt_gb = round(bt / 1_000_000_000, 2)
        
        # Get current state from DB
        state, state_mk = db.get_user_state(uname)
        
        # Threshold check using per-user limit
        limit_bytes = int(user_threshold_gb * 1_000_000_000)

        # Scenario 1: Needs throttling
        if bt >= limit_bytes:
            logger.info(f"User {uname} is over threshold: {bt_gb} GB")
            if state != 'throttled' or state_mk != mk:
                # ACTION: Throttle via Profile
                logger.info(f"FUP Engine: Throttling user {uname} via Profile {THROTTLE_RATE}")
                
                success, err = mikrotik_client.set_pppoe_profile(uname, THROTTLE_RATE)
                if success:
                    mikrotik_client.disconnect_pppoe_user(uname)
                    db.set_user_state(uname, mk, 'throttled', reason=f"Usage {bt_gb} GB >= {user_threshold_gb} GB")
                    db.log_action(uname, 'THROTTLE', f"Applied profile {THROTTLE_RATE}, usage {bt_gb} GB")
                    notifications.append(
                        f"⚠️ *FUP Alert: {uname}*\n"
                        f"Usage: `{bt_gb} GB` >= `{user_threshold_gb} GB`.\n"
                        f"Profile diubah ke `{THROTTLE_RATE}`."
                    )
                else:
                    notifications.append(f"❌ Gagal throttle `{uname}`: {err}")
        
        # Scenario 1B: Warning notifications (80%, 90%)
        elif state != 'throttled' or state_mk != mk:
            pct = (bt / limit_bytes) * 100
            if 80 <= pct < 81: # Very narrow range to avoid spamming every cycle
                notifications.append(f"📢 *FUP Warning: {uname}*\nPemakaian sudah mencapai `80%` ({bt_gb} GB / {user_threshold_gb} GB)")
            elif 90 <= pct < 91:
                notifications.append(f"📢 *FUP Warning: {uname}*\nPemakaian sudah mencapai `90%` ({bt_gb} GB / {user_threshold_gb} GB)")
        
        # Scenario 2: Monthly reset (if they were throttled in previous month or state is missing for this month)
        # Note: Unthrottle mostly happens at start of month.
        # If we see a user in 'throttled' state but the month_key is different, we should reset them.
        elif state == 'throttled' and state_mk != mk:
            logger.info(f"FUP Engine: Resetting user {uname} to normal profile (Bulan baru)")
            success, err = mikrotik_client.set_pppoe_profile(uname, BASE_RATE)
            if success:
                mikrotik_client.disconnect_pppoe_user(uname)
                db.set_user_state(uname, mk, 'normal', reason="Monthly reset")
                db.log_action(uname, 'UNTHROTTLE', f"Reset to profile {BASE_RATE} due to new month {mk}")
                notifications.append(
                    f"✅ *FUP Reset: {uname}*\n"
                    f"Bulan baru `{mk}`. Profile dikembalikan ke `{BASE_RATE}`."
                )
            else:
                notifications.append(f"❌ Gagal reset `{uname}`: {err}")
                
        # Scenario 3: Initial state for the month
        elif state is None or state_mk != mk:
            db.set_user_state(uname, mk, 'normal', reason="Initial check for month")

    conn.close()
    return notifications
