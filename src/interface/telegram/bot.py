import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from src.config import Config
from src.application.fup_service import FupService
from src.application.admin_service import AdminService
from src.application.billing_service import BillingService
from src.infrastructure.database.repository import SqliteRepository
from src.infrastructure.mikrotik.gateway import MikrotikGateway

logger = logging.getLogger('mikrotik-bot.interface.telegram')

class TelegramBotInterface:
    def __init__(self, fup_service: FupService, admin_service: AdminService, billing_service: BillingService, repo: SqliteRepository, mk_gateway: MikrotikGateway):
        self.fup_service = fup_service
        self.admin_service = admin_service
        self.billing_service = billing_service
        self.repo = repo
        self.mk_gateway = mk_gateway

    def setup_handlers(self, app: Application):
        app.add_handler(CommandHandler('start', self.cmd_start))
        app.add_handler(CommandHandler('chatid', self.cmd_chatid))
        app.add_handler(CommandHandler('status', self.cmd_status))
        app.add_handler(CommandHandler('top', self.cmd_top))
        app.add_handler(CommandHandler('summary', self.cmd_summary))
        app.add_handler(CommandHandler('users', self.cmd_users))
        app.add_handler(CommandHandler('sessions', self.cmd_sessions))
        app.add_handler(CommandHandler('add_user', self.cmd_add_user))
        app.add_handler(CommandHandler('del_user', self.cmd_del_user))
        app.add_handler(CommandHandler('kick', self.cmd_kick))
        app.add_handler(CommandHandler('logs', self.cmd_logs))
        app.add_handler(CommandHandler('throttled', self.cmd_throttled))
        app.add_handler(CommandHandler('set_limit', self.cmd_set_limit))
        app.add_handler(CommandHandler('set_enabled', self.cmd_set_enabled))
        app.add_handler(CommandHandler('force_throttle', self.cmd_force_throttle))
        app.add_handler(CommandHandler('force_normal', self.cmd_force_normal))
        app.add_handler(CommandHandler('runcheck', self.cmd_runcheck))
        app.add_handler(CommandHandler('health', self.cmd_health))
        
        # Billing Handlers
        app.add_handler(CommandHandler('pay', self.cmd_pay))
        app.add_handler(CommandHandler('billing', self.cmd_billing))
        app.add_handler(CommandHandler('unpaid', self.cmd_unpaid))
        app.add_handler(CommandHandler('wa', self.cmd_set_wa))
        
        app.add_handler(CallbackQueryHandler(self.handle_callback))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "🛰 *MikroTik Pro Manager v8.5*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💰 *Billing & Payment*\n"
            "• /pay <u|amount> - Catat bayar & aktifkan\n"
            "• /billing <user> - Cek status bayar user\n"
            "• /unpaid - Daftar penunggak bulan ini\n\n"
            "📊 *Monitoring (FUP)*\n"
            "• /status <user> - Detail & IP MikroTik\n"
            "• /summary - Ringkasan traffic\n"
            "• /users - Daftar semua user & WA\n\n"
            "⚙️ *Admin Tool*\n"
            "• /add_user <u|p|prof> - Tambah PPPoE\n"
            "• /wa <u|number> - Set Nomor WhatsApp\n"
            "• /del_user <user> - Hapus PPPoE\n"
            "• /kick <user> - Putus sesi aktif\n"
            "• /health - Status bot & router\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def cmd_chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(f"ID Chat ini: `{update.effective_chat.id}`", parse_mode='Markdown')

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format: `/status <username>`", parse_mode='Markdown')
            return
        
        username = context.args[0]
        mk = Config.month_key()
        
        bt = self.repo.get_accumulated_bytes(mk, username)
        usage_gb = Config.to_gb(bt)
        
        user_state_obj = self.repo.get_user_state(username)
        state = user_state_obj.state if user_state_obj else 'normal'
        last_action = user_state_obj.last_action_at if user_state_obj else "N/A"
        
        enabled, threshold_gb = self.repo.get_user_config(username)
        target_p = Config.THROTTLE_RATE if state == 'throttled' else Config.BASE_RATE
        
        profile = self.repo.get_user_profile(username)
        pkg_info = Config.get_package_info(profile)
        wa = self.repo.get_user_whatsapp(username) or "Belum di-set"
        
        # MikroTik Dynamic Data
        mk_secret = self.mk_gateway.get_ppp_secret_details(username)
        remote_address = mk_secret.get('remote-address') if mk_secret else "N/A"
        
        msg = (
            f"👤 *User Status: {username}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Paket:* `{pkg_info['name']}`\n"
            f"💰 *Harga:* `Rp {pkg_info['price']:,.0f}`\n"
            f"📊 *Usage:* `{usage_gb} GB` / `{threshold_gb} GB`\n"
            f"📱 *WhatsApp:* `{wa}`\n"
            f"📍 *Static IP:* `{remote_address}`\n"
            f"⚙️ *State:* `{state.upper()}`\n"
            f"📅 *Bulan:* `{mk}`\n"
            f"🔄 *Last Action:* `{last_action}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 *Speed Saat Ini:* `{target_p}`"
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
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def cmd_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        users = self.repo.get_all_users_config()
        if not users:
            await update.message.reply_text("Belum ada data user di database.")
            return

        lines = ["👥 *Daftar User & Config*"]
        for uname, enabled, thresh, profile, wa in users:
            status = "✅" if enabled else "❌"
            limit_str = f"{thresh} GB" if thresh is not None else f"{Config.FUP_THRESHOLD_GB} GB"
            pkg_name = Config.get_package_info(profile)['name']
            wa_str = f" | 📱 `{wa}`" if wa else ""
            lines.append(f"- `{uname}` ({pkg_name}): {status} | Limit: *{limit_str}*{wa_str}")
        
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        mk = Config.month_key()
        top = self.repo.get_top_usage(mk, limit=10)
        if not top:
            await update.message.reply_text("Belum ada data pemakaian untuk bulan ini.")
            return

        lines = [f"🏆 *Top 10 Usage ({mk})*"]
        for i, (uname, bt) in enumerate(top, 1):
            gb = Config.to_gb(bt)
            lines.append(f"{i}. `{uname}`: *{gb} GB*")
        
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        total, top = self.admin_service.get_summary_data()
        total_gb = Config.to_gb(total)
        mk = Config.month_key()
        
        lines = [f"📊 *Network Summary ({mk})*"]
        lines.append(f"🌐 *Total Traffic:* `{total_gb} GB`")
        lines.append("\n🔝 *Top 5 Users:*")
        
        if top:
            for i, (uname, bt) in enumerate(top, 1):
                gb = Config.to_gb(bt)
                lines.append(f"{i}. `{uname}`: `{gb} GB`")
        else:
            lines.append("_Belum ada data pemakaian._")
            
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def cmd_sessions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        actives = self.admin_service.fetch_active_sessions()
        if not actives:
            await update.message.reply_text("Tidak ada user PPPoE yang aktif saat ini.")
            return
        
        lines = [f"🌐 *Active Sessions ({len(actives)})*"]
        for s in actives:
            name = s.get('name', 'N/A')
            addr = s.get('address', 'N/A')
            uptime = s.get('uptime', 'N/A')
            lines.append(f"👤 `{name}`\n  ├ IP: `{addr}`\n  └ Uptime: `{uptime}`")
        
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def cmd_add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) < 3:
            await update.message.reply_text("Format: `/add_user <username> <password> <profile>`", parse_mode='Markdown')
            return
        
        uname, pwd, prof = context.args[0], context.args[1], context.args[2]
        success, ip, err = self.admin_service.add_user(uname, pwd, prof)
        
        if success:
            await update.message.reply_text(
                f"✅ *User Berhasil Dibuat!*\n"
                f"Username: `{uname}`\n"
                f"Password: `{pwd}`\n"
                f"Profile: `{prof}`\n"
                f"Static IP: `{ip}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Gagal menambah user: {err}")

    async def cmd_del_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format: `/del_user <username>`", parse_mode='Markdown')
            return
        uname = context.args[0]
        success, err = self.admin_service.delete_user(uname)
        if success:
            await update.message.reply_text(f"✅ Secret `{uname}` berhasil dihapus dari MikroTik.")
        else:
            await update.message.reply_text(f"❌ Gagal hapus user: {err}")

    async def cmd_kick(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format: `/kick <username>`", parse_mode='Markdown')
            return
        uname = context.args[0]
        success, err = self.admin_service.kick_user(uname)
        if success:
            await update.message.reply_text(f"✅ Sesi aktif `{uname}` telah diputuskan.")
        else:
            await update.message.reply_text(f"❌ Gagal kick user: {err}")

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format: `/logs <username>`", parse_mode='Markdown')
            return
        username = context.args[0]
        logs = self.repo.get_action_logs(username)
        if not logs:
            await update.message.reply_text(f"Tidak ada riwayat untuk user `{username}`.")
            return
        
        lines = [f"📜 *History: {username}*"]
        for ts, action, detail in logs:
            try:
                dt = datetime.fromisoformat(ts).strftime('%d/%m %H:%M')
            except:
                dt = ts
            lines.append(f"• `[{dt}]` *{action}*: {detail}")
            
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def cmd_throttled(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        mk = Config.month_key()
        users = self.repo.get_throttled_users(mk)
        if not users:
            await update.message.reply_text("Tidak ada user yang sedang di-limit.")
            return
        
        lines = ["🔽 *User Throttled (Current Month)*"]
        for uname, ts, reason in users:
            try:
                dt = datetime.fromisoformat(ts).strftime('%d/%m %H:%M')
            except:
                dt = ts
            lines.append(f"- `{uname}`: `[{dt}]` {reason}")
            
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def cmd_set_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) < 2:
            await update.message.reply_text("Format: `/set_limit <user> <gb>`", parse_mode='Markdown')
            return
        uname, limit = context.args[0], float(context.args[1])
        self.admin_service.update_user_limit(uname, limit)
        await update.message.reply_text(f"✅ Limit user `{uname}` telah diubah ke `{limit} GB`.")

    async def cmd_set_enabled(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) < 2:
            await update.message.reply_text("Format: `/set_enabled <user> <1/0>`", parse_mode='Markdown')
            return
        uname, enabled = context.args[0], context.args[1] == '1'
        self.admin_service.toggle_user_fup(uname, enabled)
        status = "AKTIF" if enabled else "MATI"
        await update.message.reply_text(f"✅ Auto-FUP untuk `{uname}` sekarang *{status}*.")

    async def cmd_force_throttle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format: `/force_throttle <username>`", parse_mode='Markdown')
            return
        uname = context.args[0]
        success, err = self.mk_gateway.set_pppoe_profile(uname, Config.THROTTLE_RATE)
        if success:
            self.admin_service.kick_user(uname)
            self.repo.save_user_state(UserState(uname, Config.month_key(), 'throttled', Config.now_local().isoformat(), "Manual force throttle"))
            await update.message.reply_text(f"✅ `{uname}` berhasil di-limit manual.")
        else:
            await update.message.reply_text(f"❌ Gagal throttle: {err}")

    async def cmd_force_normal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format: `/force_normal <username>`", parse_mode='Markdown')
            return
        uname = context.args[0]
        success, err = self.mk_gateway.set_pppoe_profile(uname, Config.BASE_RATE)
        if success:
            self.admin_service.kick_user(uname)
            self.repo.save_user_state(UserState(uname, Config.month_key(), 'normal', Config.now_local().isoformat(), "Manual force normal"))
            await update.message.reply_text(f"✅ `{uname}` dikembalikan ke normal manual.")
        else:
            await update.message.reply_text(f"❌ Gagal unlimit: {err}")

    async def cmd_runcheck(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text('🔄 Menjalankan FUP check manual...')
        notifs = self.fup_service.run_fup_cycle()
        if not notifs:
            await update.message.reply_text('✅ Selesai. Tidak ada aksi baru.')
        else:
            for msg in notifs:
                await update.message.reply_text(msg, parse_mode='Markdown')

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tcp_ok, ms, tcp_err = self.mk_gateway.tcp_check()
        api_ok, info, api_err = self.mk_gateway.get_api_health()
        
        latency_str = f"{ms}ms" if tcp_ok else "N/A"
        status_text = (
            f"🏥 *System Health Check*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛰 *TCP ({Config.MIKROTIK_PORT}):* {'✅ UP' if tcp_ok else '❌ DOWN'}\n"
            f"📡 *API Protocol:* {'✅ OK' if api_ok else '❌ FAIL'}\n"
            f"⏳ *Latency:* `{latency_str}`\n"
            f"👤 *Identity:* `{info['identity'] if api_ok else 'N/A'}`\n"
            f"🆙 *Uptime:* `{info['uptime'] if api_ok else 'N/A'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        if not api_ok:
            status_text += f"\n⚠️ *Error:* `{api_err}`"
        await update.message.reply_text(status_text, parse_mode='Markdown')

    # --- Billing Commands ---

    async def cmd_pay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) < 2:
            await update.message.reply_text("Format: `/pay <username> <amount>`", parse_mode='Markdown')
            return
        
        username = context.args[0]
        try:
            amount = float(context.args[1].replace(',', ''))
        except:
            await update.message.reply_text("❌ Jumlah pembayaran harus berupa angka.")
            return

        success, msg = self.billing_service.process_payment(username, amount)
        if success:
            await update.message.reply_text(f"✅ *Sukses!*\n{msg}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Gagal: {msg}")

    async def cmd_billing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format: `/billing <username>`", parse_mode='Markdown')
            return
        
        username = context.args[0]
        mk = Config.month_key()
        status = self.repo.get_billing_status(username, mk)
        profile = self.repo.get_user_profile(username)
        pkg_info = Config.get_package_info(profile)
        
        if not status:
            msg = (
                f"💰 *Billing: {username} ({mk})*\n"
                f"Paket: `{pkg_info['name']}`\n"
                f"Status: `❌ BELUM BAYAR`\n"
                f"Tagihan: `Rp {pkg_info['price']:,.0f}`"
            )
            await update.message.reply_text(msg, parse_mode='Markdown')
            return
            
        is_paid, amount, ts = status
        try:
            dt = datetime.fromisoformat(ts).strftime('%d/%m/%Y %H:%M')
        except:
            dt = ts
            
        msg = (
            f"💰 *Billing: {username} ({mk})*\n"
            f"Paket: `{pkg_info['name']}`\n"
            f"Status: `{'✅ LUNAS' if is_paid else '❌ BELUM BAYAR'}`\n"
            f"Total Bayar: `Rp {amount:,.0f}`\n"
            f"Update Terakhir: `{dt}`"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

    async def cmd_unpaid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        mk = Config.month_key()
        unpaid_data = self.repo.get_unpaid_with_profile(mk)
        
        if not unpaid_data:
            await update.message.reply_text(f"✅ Semua user sudah lunas untuk bulan `{mk}`.")
            return
            
        lines = [f"💸 *Penunggak Bulan {mk} ({len(unpaid_data)})*", "_Jatuh tempo setiap tanggal 20_"]
        total_piutang = 0
        for uname, profile in unpaid_data:
            pkg_info = Config.get_package_info(profile)
            total_piutang += pkg_info['price']
            lines.append(f"- `{uname}` ({pkg_info['name']}): *Rp {pkg_info['price']:,.0f}*")
        
        lines.append(f"\nTotal Piutang: *Rp {total_piutang:,.0f}*")
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def cmd_set_wa(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) < 2:
            await update.message.reply_text("Format: `/wa <username> <nomor>`", parse_mode='Markdown')
            return
        
        username = context.args[0]
        wa_number = context.args[1]
        
        # Current data to preserve other fields
        profile = self.repo.get_user_profile(username)
        self.repo.register_user(username, username, f"<pppoe-{username}>", profile, wa_number)
        
        await update.message.reply_text(f"✅ Nomor WhatsApp untuk `{username}` berhasil diset ke `{wa_number}`.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data.split(':')
        action, username = data[0], data[1]
        
        if action == "refresh":
            # Just redo status logic
            await self.cmd_status_edit(query, username)
        elif action == "kick":
            success, err = self.admin_service.kick_user(username)
            await query.message.reply_text(f"✅ User `{username}` kicked." if success else f"❌ Error: {err}")
        elif action == "toggle":
            user_state_obj = self.repo.get_user_state(username)
            state = user_state_obj.state if user_state_obj else 'normal'
            if state == 'throttled':
                success, err = self.mk_gateway.set_pppoe_profile(username, Config.BASE_RATE)
                if success:
                    self.admin_service.kick_user(username)
                    self.repo.save_user_state(UserState(username, Config.month_key(), 'normal', Config.now_local().isoformat(), "Manual unlimit via button"))
                    await query.message.reply_text(f"✅ `{username}` dikembalikan ke normal.")
            else:
                success, err = self.mk_gateway.set_pppoe_profile(username, Config.THROTTLE_RATE)
                if success:
                    self.admin_service.kick_user(username)
                    self.repo.save_user_state(UserState(username, Config.month_key(), 'throttled', Config.now_local().isoformat(), "Manual limit via button"))
                    await query.message.reply_text(f"✅ `{username}` berhasil di-limit.")
            await self.cmd_status_edit(query, username)
        elif action == "logs":
            context.args = [username]
            msg_mock = type('MockUpdate', (), {'message': query.message})
            await self.cmd_logs(msg_mock, context)

    async def cmd_status_edit(self, query, username):
        mk = Config.month_key()
        bt = self.repo.get_accumulated_bytes(mk, username)
        bt_gb = Config.to_gb(bt)
        user_state_obj = self.repo.get_user_state(username)
        state = user_state_obj.state if user_state_obj else 'normal'
        enabled, threshold = self.repo.get_user_config(username)
        target_p = Config.THROTTLE_RATE if state == 'throttled' else Config.BASE_RATE
        
        msg = (
            f"📊 *Status {username}*\n"
            f"- State: `{state.upper()}`\n"
            f"- Target Profile: `{target_p}`\n"
            f"- Limit: `{threshold} GB`\n"
            f"- Monitoring: `{'✅ ON' if enabled else '❌ OFF'}`\n"
            f"- Bulan: `{mk}`\n"
            f"- Total Usage: `*{bt_gb} GB*`\n\n"
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
