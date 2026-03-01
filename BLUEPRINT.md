# 🛰️ MikroTik FUP Manager — Blueprint (Clean Architecture v7.0)

## 1) Tujuan
Membuat sistem monitoring PPPoE yang berjalan di Docker untuk manajemen kuota otomatis:
- **Normal Profile**: Managed via profile (e.g. `NORMAL`) - Speed penuh.
- **Throttled Profile**: Otomatis turun ke profile limit (e.g. `LIMIT`) jika pemakaian **>= Threshold**.
- **Enforcement**: Perubahan profile dipastikan aktif dengan **disconnect 1x**.
- **Monthly Reset**: Awal bulan berikutnya otomatis kembali ke speed normal dan reset akumulasi.

---

## 2) Prinsip Desain (Clean Architecture)
Sistem ini menggunakan prinsip **Clean Architecture (Domain-Driven Design Lite)** untuk memisahkan logika bisnis dari detail teknis:
1. **Domain Layer**: Entitas inti (User, Usage, ActionLog) yang independen.
2. **Application Layer**: Use Cases (FupService, AdminService) untuk alur kerja bisnis.
3. **Infrastructure Layer**: Adapter teknis (MikrotikGateway, SqliteRepository).
4. **Interface Layer**: Entry points (TelegramBotInterface, BackgroundWorker).

---

## 3) Arsitektur Komponen
- **`src/`**: Folder utama kode sumber.
  - **`domain/`**: Model data & kontrak bisnis.
  - **`application/`**: Logika FUP & Administrasi.
  - **`infrastructure/`**: Komunikasi MikroTik API & Database SQLite.
  - **`interface/`**: Handler Telegram & Worker Background.
- **`data/`**: Volume Docker untuk database persistent (`bot.db`).
- **`.env`**: Konfigurasi rahasia (Token, Password, Host).

---

## 4) Folder Struktur (Current v7.0)
```text
/root/mikrotik-bot/
  ├─ src/
  │   ├─ domain/          # Models (User, Usage, State)
  │   ├─ application/     # Services (FUP, Admin)
  │   ├─ infrastructure/  # Gateways (MikroTik, DB Repository)
  │   ├─ interface/       # Presentation (Telegram Bot, Worker)
  │   ├─ config.py        # Centralized Config
  │   └─ main.py          # Entry Point
  ├─ data/
  │   └─ bot.db           # SQLite persistent storage
  ├─ .env                 # Environment variables
  ├─ Dockerfile           # Python 3.11 image definition
  ├─ docker-compose.yml   # Multi-container orchestration
  ├─ .gitignore           # Security prevent leaks
  └─ README.md            # Documentation & Usage Guide
```

---

## 5) Data Model (SQLite Repository)
- **`users`**: Nama user, pppoe name, status monitoring, dan custom threshold.
- **`monthly_usage`**: Akumulasi bytes per bulan (`YYYY-MM`).
- **`user_state`**: State saat ini (`normal`/`throttled`) dan alasan aksi terakhir.
- **`action_log`**: Histori audit semua perintah dan perubahan state.

---

## 6) Logic Utama
### A. Background Worker (Interval Check)
Berjalan setiap X detik:
1. **Fetch Usage**: Ambil statistik bytes dari MikroTik API (Queue Simple).
2. **Delta Calculation**: Update DB dengan menghitung selisih counter (aman terhadap reset/reboot).
3. **Threshold Check**: Bandingkan total GB bulan ini dengan limit user.
4. **Action**: Jika over limit, laksanakan throttle profile + disconnect + notif Telegram.

### B. Scheduler Tasks
1. **Monthly Rollover**: Setiap tanggal 1, reset semua user ke profile normal.
2. **Daily Report**: Setiap jam 08:00 WIB, kirim ringkasan traffic total ke admin.
3. **Daily Backup**: Setiap jam 00:00 WIB, kirim file `bot.db` ke Telegram admin.

---

## 7) Telegram Interface & UI
- **Interactive Messages**: Menggunakan Inline Buttons (Refresh, Kick, Toggle Limit, Logs).
- **Commands**:
  - `/status <user>`: Dashboard pemakaian interaktif.
  - `/summary`: Ringkasan traffic jaringan & top users.
  - `/add_user`: Tambah user baru dengan alokasi IP otomatis.
  - `/set_limit`: Kustomisasi limit GB per user.
  - `/health`: Cek kesehatan koneksi TCP & API MikroTik.

---

## 8) Konfigurasi `.env` (Required)
- `BOT_TOKEN`: Token dari BotFather.
- `TELEGRAM_CHAT_ID`: ID Admin penerima laporan.
- `MIKROTIK_HOST`: IP/Host MikroTik.
- `MIKROTIK_PORT`: Default `8728` (API).
- `MIKROTIK_USER` & `MIKROTIK_PASS`: Kredensial API RouterOS.
- `FUP_THRESHOLD_GB`: Limit default global.
- `BASE_RATE` & `THROTTLE_RATE`: Nama Profil MikroTik.

---

## 9) Roadmap Implementasi
1. **Phase 1-3**: Dasar koneksi, collector usage, dan engine FUP (Basics).
2. **Phase 4-5**: Automated monthly reset & advanced commands (Reporting).
3. **Phase 6**: Interactive UI (Inline Buttons & Session Management).
4. **Phase 7**: **Clean Architecture Refactor** (Modularization & Stability). - **[CURRENT]**

---

## 10) Security Policy
- Tidak ada kredensial di dalam kode (Strict `.env`).
- Database (`bot.db`) tidak di-track oleh Git.
- Akses Telegram dibatasi hanya untuk Admin Chat ID yang terdaftar.
