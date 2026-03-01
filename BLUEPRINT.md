# MikroTik PPPoE FUP Telegram Bot — Blueprint (Docker)

## 1) Tujuan
Membuat sistem monitoring PPPoE yang berjalan di home-server (Docker):
- Paket dasar user: **5M/5M**
- Jika pemakaian bulan berjalan **>= 100 GB**: turunkan ke **2M/2M**
- Perubahan limit dipastikan aktif dengan **disconnect 1x**
- Awal bulan berikutnya: kembali ke **5M/5M** dan hitung ulang dari nol

---

## 2) Prinsip desain
1. **Metering bulanan jangan bergantung penuh pada counter live RouterOS**
   - Counter bisa berubah/reset karena reboot/reconnect.
   - Bot menyimpan akumulasi bulanan di DB lokal.
2. **Idempotent action**
   - Jika user sudah throttled, jangan eksekusi throttle berulang-ulang.
3. **Aman & bisa diaudit**
   - Semua aksi (throttle, unthrottle, disconnect, error) masuk log + notifikasi Telegram.

---

## 3) Arsitektur komponen
- **app (Python)**
  - Scheduler internal (interval check + monthly reset)
  - Logic FUP
  - Telegram command handler
  - MikroTik connector (SSH/API)
- **db (SQLite file di volume Docker)**
  - Simpan state user, usage bulanan, histori aksi
- **config (.env)**
  - Token telegram, threshold, profil speed, kredensial MikroTik

Opsional nanti:
- Redis untuk queue job
- Postgres kalau scale besar

---

## 4) Folder struktur (target)
```
/root/mikrotik-bot/
  ├─ docker-compose.yml
  ├─ .env
  ├─ app/
  │   ├─ main.py
  │   ├─ mikrotik_client.py
  │   ├─ fup_engine.py
  │   ├─ scheduler.py
  │   ├─ telegram_bot.py
  │   └─ db.py
  ├─ data/
  │   ├─ bot.db
  │   └─ logs/
  ├─ scripts/
  │   ├─ backup_db.sh
  │   └─ restore_db.sh
  └─ BLUEPRINT.md
```

---

## 5) Data model (SQLite)

### table: `users`
- `username` (PK) — contoh: `ilham`
- `pppoe_name` — contoh: `ilham`
- `queue_name` — contoh: `<pppoe-ilham>`
- `base_rate` — default `5M/5M`
- `throttle_rate` — default `2M/2M`
- `enabled` — 1/0

### table: `monthly_usage`
- `id` (PK)
- `month_key` — format `YYYY-MM` (contoh `2026-03`)
- `username`
- `bytes_in`
- `bytes_out`
- `bytes_total`
- `last_sample_at`

### table: `user_state`
- `username` (PK)
- `month_key`
- `state` — `normal` | `throttled`
- `last_action_at`
- `last_reason`

### table: `action_log`
- `id` (PK)
- `ts`
- `username`
- `action` — `THROTTLE`, `UNTHROTTLE`, `DISCONNECT`, `ERROR`, `RESET_MONTH`
- `detail`

---

## 6) Sumber data usage
Prioritas:
1. Counter dari queue/user yang konsisten antar reconnect
2. Snapshot periodik ke DB (mis. tiap 5 menit)
3. Hitung delta aman (hindari minus jika counter turun/reset)

Aturan delta:
- Jika counter sekarang >= counter sebelumnya: `delta = now - prev`
- Jika counter sekarang < sebelumnya: anggap rollover/reset -> `delta = now` + catat event reset

---

## 7) Alur logic utama

### A. Interval check (mis. tiap 5 menit)
Untuk tiap user aktif:
1. Ambil counter terbaru
2. Update akumulasi `monthly_usage`
3. Jika `bytes_total >= threshold` DAN state `normal`:
   - Apply rate `2M/2M`
   - Disconnect PPP aktif user (1x)
   - Ubah state -> `throttled`
   - Kirim notif Telegram

### B. Monthly rollover (tgl 1, 00:00 Asia/Jakarta)
1. Buat `month_key` baru
2. Set semua state user -> `normal`
3. Apply base rate `5M/5M`
4. (Opsional) disconnect terjadwal/bertahap agar profil langsung refresh
5. Kirim ringkasan Telegram

---

## 8) Telegram commands (MVP)
- `/health` -> status service, koneksi MikroTik, DB
- `/status <user>` -> state, usage bulan ini, rate aktif
- `/top` -> pengguna terbesar bulan ini
- `/throttled` -> daftar user throttled
- `/force_throttle <user>` -> throttle manual
- `/force_normal <user>` -> balik normal manual
- `/run_check` -> trigger pengecekan sekarang

---

## 9) Konfigurasi `.env` (rencana)
- `TZ=Asia/Jakarta`
- `BOT_TOKEN=...`
- `TELEGRAM_CHAT_ID=...`
- `MIKROTIK_HOST=192.168.100.1`
- `MIKROTIK_PORT=2222`
- `MIKROTIK_USER=...`
- `MIKROTIK_PASS=...`
- `CHECK_INTERVAL_SECONDS=300`
- `FUP_THRESHOLD_GB=100`
- `BASE_RATE=5M/5M`
- `THROTTLE_RATE=2M/2M`

---

## 10) Docker runtime plan
- Single container `mikrotik-bot` (restart always)
- Volume persist:
  - `./data:/app/data`
  - `./.env:/app/.env:ro`
- Healthcheck endpoint/log-based

---

## 11) Failure handling
- MikroTik unreachable -> retry exponential backoff + notif warning
- Telegram API error -> log + retry
- DB lock -> retry ringan
- Eksekusi action gagal -> jangan ubah state, kirim alert

---

## 12) Security baseline
- Simpan kredensial di `.env` (permission `600`)
- Jangan hardcode password di source
- Batasi akses Telegram command ke chat id admin
- Backup `data/bot.db` harian

---

## 13) Tahapan implementasi (pelan-pelan)
1. **Phase 1:** scaffold Docker + koneksi MikroTik + `/health`
2. **Phase 2:** collector usage + simpan DB
3. **Phase 3:** engine FUP auto throttle + disconnect + notif
4. **Phase 4:** monthly reset otomatis
5. **Phase 5:** command admin tambahan + report ringkas

---

## 14) Catatan untuk topologi kamu
- Home-server (192.168.1.48) bisa akses MikroTik via `192.168.1.119:2222` (sudah terbukti)
- Eksekusi WOL dan automasi jaringan tetap dari home-server memungkinkan
- Untuk FUP ini, gunakan endpoint MikroTik yang konsisten dari home-server
