import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
import db
import mikrotik_client
import fup_engine

ADMIN_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()
TZ = os.getenv('TZ', 'Asia/Jakarta')
CHECK_INTERVAL_SECONDS = os.getenv('CHECK_INTERVAL_SECONDS', '300')

def to_gb(n: int) -> float:
    return round(n / 1_000_000_000, 2)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🚀 *MikroTik FUP Bot Ready*\n\n"
        "*Commands:*\n"
        "• /health - Cek status bot & koneksi MikroTik\n"
        "• /status <user> - Detail usage & status user\n"
        "• /top - 10 pemakaian tertinggi bulan ini\n"
        "• /summary - Ringkasan pemakaian hari ini\n"
        "• /users - Daftar semua user & konfigurasi\n"
        "• /sessions - Daftar user yang sedang online\n"
        "• /throttled - Daftar user yang saat ini di-limit\n"
        "• /logs <user> - Riwayat aksi FUP untuk user\n"
        "• /add_user <u|p|prof> - Tambah user baru (Auto IP)\n"
        "• /del_user <user> - Hapus secret dari MikroTik\n"
        "• /kick <user> - Putuskan sesi user aktif\n"
        "• /set_limit <user> <gb> - Set limit khusus user\n"
        "• /set_enabled <user> <0/1> - Aktifkan/matikan FUP user\n"
        "• /force_throttle <user> - Limit manual\n"
        "• /force_normal <user> - Unlimit manual\n"
        "• /runcheck - Jalankan siklus pengecekan manual"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'chat_id: {update.effective_chat.id}')

async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ['🩺 *Health Check*', f'- Timezone: `{TZ}`', f'- Interval: `{CHECK_INTERVAL_SECONDS}s`']
    
    tcp_ok, latency, tcp_err = mikrotik_client.tcp_check()
    if tcp_ok:
        lines.append(f'- TCP MikroTik: ✅ ({latency} ms)')
    else:
        lines.append(f'- TCP MikroTik: ❌ ({tcp_err})')

    api_ok, info, api_err = mikrotik_client.get_api_health()
    if api_ok and info:
        lines.extend([
            '- API login: ✅',
            f"- Identity: `{info['identity']}`",
            f"- RouterOS: `{info['version']}`",
        ])
    else:
        lines.append(f'- API login: ❌ ({api_err})')

    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM users WHERE enabled=1')
    ucount = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM monthly_usage WHERE month_key=?', (fup_engine.month_key(),))
    mcount = cur.fetchone()[0]
    conn.close()
    
    lines.append(f'- DB users aktif: `{ucount}`')
    lines.append(f'- DB usage bulan ini: `{mcount}`')

    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Format: /status <username>')
        return
    username = context.args[0].strip().lower()
    mk = fup_engine.month_key()
    
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('SELECT queue_name FROM users WHERE username=?', (username,))
    u = cur.fetchone()
    cur.execute('SELECT bytes_total, last_sample_at FROM monthly_usage WHERE month_key=? AND username=?', (mk, username))
    d = cur.fetchone()
    cur.execute('SELECT state FROM user_state WHERE username=?', (username,))
    s = cur.fetchone()
    conn.close()

    if not d:
        await update.message.reply_text(f'Data `{username}` belum ada di DB bulan `{mk}`.')
        return

    bt, ts = d
    state = s[0] if s else 'normal'
    qname = u[0] if u else f'<pppoe-{username}>'
    u_enabled, user_thresh = db.get_user_config(username)
    target_p = os.getenv('THROTTLE_RATE', 'LIMIT') if state == 'throttled' else os.getenv('BASE_RATE', 'Ilham')
    
    # Format timestamp to WIB
    # ts is ISO format from now_local().isoformat()
    try:
        dt = datetime.fromisoformat(ts)
        last_sample_str = dt.strftime('%d/%m/%Y %H:%M') + " WIB"
    except:
        last_sample_str = ts

    msg = (
        f"📊 *Status {username}*\n"
        f"- State: `{state.upper()}`\n"
        f"- Target Profile: `{target_p}`\n"
        f"- Limit: `{user_thresh} GB`\n"
        f"- Monitoring: `{'✅ ON' if u_enabled else '❌ OFF'}`\n"
        f"- Bulan: `{mk}`\n"
        f"- Usage: `*{to_gb(bt)} GB*`\n"
        f"- Last sample: `{last_sample_str}`"
    )

    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh:{username}"),
            InlineKeyboardButton("🚫 Kick", callback_data=f"kick:{username}")
        ],
        [
            InlineKeyboardButton("🔽 Limit" if state == 'normal' else "🔼 Unlimit", callback_data=f"toggle:{username}"),
            InlineKeyboardButton("📜 Logs", callback_data=f"logs:{username}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)

async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mk = fup_engine.month_key()
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('''
        SELECT username, bytes_total
        FROM monthly_usage
        WHERE month_key=?
        ORDER BY bytes_total DESC
        LIMIT 10
    ''', (mk,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text('Belum ada data usage bulan ini.')
        return

    lines = [f'🏆 *Top Usage {mk}*']
    for i, (u, bt) in enumerate(rows, 1):
        lines.append(f'{i}. `{u}` — *{to_gb(bt)} GB*')
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')

async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Format: /logs <username>')
        return
    username = context.args[0].strip().lower()
    
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('''
        SELECT ts, action, detail 
        FROM action_log 
        WHERE username=? 
        ORDER BY ts DESC 
        LIMIT 10
    ''', (username,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f'Tidak ada riwayat aksi untuk `{username}`.', parse_mode='Markdown')
        return

    lines = [f'📜 *History Aksi: {username}*']
    for ts, action, detail in rows:
        # Format timestamp to WIB
        try:
            dt = datetime.fromisoformat(ts)
            dt_str = dt.strftime('%d/%m %H:%M') + " WIB"
        except:
            dt_str = ts
        lines.append(f'- `[{dt_str}]` *{action}*\n  _{detail}_')
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')

async def cmd_throttled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mk = fup_engine.month_key()
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('''
        SELECT username, last_action_at, last_reason
        FROM user_state
        WHERE state='throttled' AND month_key=?
    ''', (mk,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f'Tidak ada user throttled di bulan `{mk}`.', parse_mode='Markdown')
        return

    lines = [f'🚫 *User Throttled ({mk})*']
    for u, ts, reason in rows:
        lines.append(f'- `{u}` (sejak {ts})\n  _{reason}_')
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')

async def cmd_force_throttle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Format: /force_throttle <username>')
        return
    username = context.args[0].strip().lower()
    
    # Check if user exists in our DB first
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('SELECT queue_name FROM users WHERE username=?', (username,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f'User `{username}` tidak ditemukan di database.')
        return
    
    qname = row[0]
    rate = os.getenv('THROTTLE_RATE', 'LIMIT')
    mk = fup_engine.month_key()
    
    success, err = mikrotik_client.set_pppoe_profile(username, rate)
    if success:
        mikrotik_client.disconnect_pppoe_user(username)
        db.set_user_state(username, mk, 'throttled', reason="Manual force throttle")
        db.log_action(username, 'FORCE_THROTTLE', f"Manual profile move to {rate}")
        await update.message.reply_text(f'✅ `{username}` berhasil dipindah ke profile `{rate}` secara manual.', parse_mode='Markdown')
    else:
        await update.message.reply_text(f'❌ Gagal throttle `{username}`: {err}')

async def cmd_force_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Format: /force_normal <username>')
        return
    username = context.args[0].strip().lower()
    
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('SELECT queue_name FROM users WHERE username=?', (username,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f'User `{username}` tidak ditemukan di database.')
        return
    
    qname = row[0]
    rate = os.getenv('BASE_RATE', 'ilham')
    mk = fup_engine.month_key()
    
    success, err = mikrotik_client.set_pppoe_profile(username, rate)
    if success:
        mikrotik_client.disconnect_pppoe_user(username)
        db.set_user_state(username, mk, 'normal', reason="Manual force normal")
        db.log_action(username, 'FORCE_NORMAL', f"Manual profile move to {rate}")
        await update.message.reply_text(f'✅ `{username}` dikembalikan ke profile normal `{rate}`.', parse_mode='Markdown')
    else:
        await update.message.reply_text(f'❌ Gagal unthrottle `{username}`: {err}')

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_all_users()
    if not rows:
        await update.message.reply_text("Belum ada user di database.")
        return
    
    lines = ["👥 *Daftar User & Config*"]
    for uname, enabled, threshold in rows:
        status = "✅ ON" if enabled else "❌ OFF"
        # Use DB's default threshold if not specifically set for user
        effective_thresh = threshold if threshold is not None else db.DEFAULT_THRESHOLD
        is_custom = "" if threshold is None else " (Custom)"
        lines.append(f"- `{uname}`: {status} | Limit: `*{effective_thresh} GB*{is_custom}`")
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

async def cmd_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Format: /set_limit <username> <gb>")
        return
    uname = context.args[0].lower()
    try:
        gb = float(context.args[1])
        db.set_user_config(uname, threshold=gb)
        await update.message.reply_text(f"✅ Limit untuk `{uname}` diatur ke `{gb} GB`.", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("Nilai GB harus angka.")

async def cmd_set_enabled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Format: /set_enabled <username> <0 atau 1>")
        return
    uname = context.args[0].lower()
    val = 1 if context.args[1] == '1' else 0
    db.set_user_config(uname, enabled=val)
    status = "AKTIF" if val else "NONAKTIF"
    await update.message.reply_text(f"✅ Monitoring FUP untuk `{uname}` sekarang *{status}*.", parse_mode='Markdown')

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mk = fup_engine.month_key()
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute('''
        SELECT username, bytes_total
        FROM monthly_usage
        WHERE month_key=?
        ORDER BY bytes_total DESC
        LIMIT 5
    ''', (mk,))
    top_rows = cur.fetchall()
    
    cur.execute('SELECT SUM(bytes_total) FROM monthly_usage WHERE month_key=?', (mk,))
    total_bytes = cur.fetchone()[0] or 0
    conn.close()
    
    lines = [
        f"📋 *Summary Report {mk}*",
        f"Total Traffic: `*{to_gb(total_bytes)} GB*`",
        "",
        "🔝 *Top 5 Users:*"
    ]
    for i, (u, bt) in enumerate(top_rows, 1):
        lines.append(f"{i}. `{u}`: {to_gb(bt)} GB")
        
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

async def cmd_runcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🔄 Menjalankan FUP check cycle...')
    notifs = fup_engine.run_fup_cycle()
    if not notifs:
        await update.message.reply_text('✅ Cycle selesai. Tidak ada aksi baru.')
    else:
        for msg in notifs:
            await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    actives = mikrotik_client.fetch_active_sessions()
    if not actives:
        await update.message.reply_text("Tidak ada user PPPoE yang aktif saat ini.")
        return
    
    lines = [f"🌐 *Active Sessions ({len(actives)})*"]
    for s in actives:
        name = s.get('name', 'N/A')
        addr = s.get('address', 'N/A')
        uptime = s.get('uptime', 'N/A')
        caller = s.get('caller-id', 'N/A')
        lines.append(f"👤 `{name}`\n  ├ IP: `{addr}`\n  ├ Time: `{uptime}`\n  └ MAC: `{caller}`")
    
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

async def cmd_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Format: `/add_user <username> <password> <profile>`", parse_mode='Markdown')
        return
    
    uname, pwd, prof = context.args[0], context.args[1], context.args[2]
    new_ip = mikrotik_client.get_next_pppoe_ip()
    
    success, err = mikrotik_client.add_ppp_secret(uname, pwd, prof, new_ip)
    if success:
        db.log_action(uname, 'ADD_USER', f"New secret created. Profile: {prof}, IP: {new_ip}")
        await update.message.reply_text(
            f"✅ *User Berhasil Dibuat!*\n"
            f"Username: `{uname}`\n"
            f"Password: `{pwd}`\n"
            f"Profile: `{prof}`\n"
            f"Static IP: `{new_ip}`",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"❌ Gagal menambah user: {err}")

async def cmd_del_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: `/del_user <username>`", parse_mode='Markdown')
        return
    uname = context.args[0]
    success, err = mikrotik_client.remove_ppp_secret(uname)
    if success:
        db.log_action(uname, 'DEL_USER', "Secret removed from MikroTik")
        await update.message.reply_text(f"✅ Secret `{uname}` berhasil dihapus dari MikroTik.")
    else:
        await update.message.reply_text(f"❌ Gagal hapus user: {err}")

async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: `/kick <username>`", parse_mode='Markdown')
        return
    uname = context.args[0]
    success, err = mikrotik_client.disconnect_pppoe_user(uname)
    if success:
        db.log_action(uname, 'KICK', "Active session kicked manually")
        await update.message.reply_text(f"✅ Sesi aktif `{uname}` telah diputuskan.")
    else:
        await update.message.reply_text(f"❌ Gagal kick user: {err}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(':')
    action = data[0]
    username = data[1]
    
    mk = fup_engine.month_key()
    
    if action == "refresh":
        # Simply re-run status logic and edit message
        # We need a helper for this or just copy-paste for now
        conn = db.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT bytes_total, last_sample_at FROM monthly_usage WHERE month_key=? AND username=?', (mk, username))
        d = cur.fetchone()
        cur.execute('SELECT state FROM user_state WHERE username=?', (username,))
        s = cur.fetchone()
        conn.close()
        
        if not d:
            await query.edit_message_text(f"Data `{username}` tidak ditemukan.")
            return

        bt, ts = d
        state = s[0] if s else 'normal'
        u_enabled, user_thresh = db.get_user_config(username)
        target_p = os.getenv('THROTTLE_RATE', 'LIMIT') if state == 'throttled' else os.getenv('BASE_RATE', 'Ilham')
        
        try:
            dt = datetime.fromisoformat(ts)
            last_sample_str = dt.strftime('%d/%m/%Y %H:%M') + " WIB"
        except:
            last_sample_str = ts
            
        msg = (
            f"📊 *Status {username}*\n"
            f"- State: `{state.upper()}`\n"
            f"- Target Profile: `{target_p}`\n"
            f"- Limit: `{user_thresh} GB`\n"
            f"- Monitoring: `{'✅ ON' if u_enabled else '❌ OFF'}`\n"
            f"- Bulan: `{mk}`\n"
            f"- Usage: `*{to_gb(bt)} GB*`\n"
            f"- Last sample: `{last_sample_str}`\n\n"
            f"_(Updated at {datetime.now().strftime('%H:%M:%S')})_"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh:{username}"),
                InlineKeyboardButton("🚫 Kick", callback_data=f"kick:{username}")
            ],
            [
                InlineKeyboardButton("🔽 Limit" if state == 'normal' else "🔼 Unlimit", callback_data=f"toggle:{username}"),
                InlineKeyboardButton("📜 Logs", callback_data=f"logs:{username}")
            ]
        ]
        await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == "kick":
        success, err = mikrotik_client.disconnect_pppoe_user(username)
        if success:
            db.log_action(username, 'KICK', "Kicked via button")
            await query.message.reply_text(f"✅ User `{username}` berhasil di-kick.")
        else:
            await query.message.reply_text(f"❌ Gagal kick: {err}")

    elif action == "toggle":
        state, _ = db.get_user_state(username)
        if state == 'throttled':
            rate = os.getenv('BASE_RATE', 'Ilham')
            success, err = mikrotik_client.set_pppoe_profile(username, rate)
            if success:
                mikrotik_client.disconnect_pppoe_user(username)
                db.set_user_state(username, mk, 'normal', reason="Manual unlimit via button")
                db.log_action(username, 'FORCE_NORMAL', f"Profile moved to {rate} (Button)")
                await query.message.reply_text(f"✅ `{username}` dikembalikan ke normal.")
        else:
            rate = os.getenv('THROTTLE_RATE', 'LIMIT')
            success, err = mikrotik_client.set_pppoe_profile(username, rate)
            if success:
                mikrotik_client.disconnect_pppoe_user(username)
                db.set_user_state(username, mk, 'throttled', reason="Manual limit via button")
                db.log_action(username, 'FORCE_THROTTLE', f"Profile moved to {rate} (Button)")
                await query.message.reply_text(f"✅ `{username}` berhasil di-limit.")
        # Refresh the status message after toggle
        context.drop_callback_data(query) # Clean up
        # We can just call the refresh logic again or better send a new status message.

    elif action == "logs":
        # Send logs as a new message
        context.args = [username]
        await cmd_logs(update, context)

def setup_handlers(app):
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('chatid', cmd_chatid))
    app.add_handler(CommandHandler('health', cmd_health))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('top', cmd_top))
    app.add_handler(CommandHandler('summary', cmd_summary))
    app.add_handler(CommandHandler('users', cmd_users))
    app.add_handler(CommandHandler('sessions', cmd_sessions))
    app.add_handler(CommandHandler('logs', cmd_logs))
    app.add_handler(CommandHandler('throttled', cmd_throttled))
    app.add_handler(CommandHandler('add_user', cmd_add_user))
    app.add_handler(CommandHandler('del_user', cmd_del_user))
    app.add_handler(CommandHandler('kick', cmd_kick))
    app.add_handler(CommandHandler('set_limit', cmd_set_limit))
    app.add_handler(CommandHandler('set_enabled', cmd_set_enabled))
    app.add_handler(CommandHandler('force_throttle', cmd_force_throttle))
    app.add_handler(CommandHandler('force_normal', cmd_force_normal))
    app.add_handler(CommandHandler('runcheck', cmd_runcheck))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
