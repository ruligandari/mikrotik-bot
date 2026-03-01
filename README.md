# 🛰️ MikroTik FUP Manager Pro

Sistem manajemen FUP (Fair Usage Policy) otomatis untuk jaringan ISP/RT-RW Net berbasis **MikroTik PPPoE**. Bot ini membantu memantau penggunaan kuota user secara real-time dan melakukan pembatasan kecepatan otomatis menggunakan sistem Profile MikroTik.

![Architecture](https://img.shields.io/badge/Architecture-Clean_DDD-blue)
![Python](https://img.shields.io/badge/Python-3.11-green)
![Docker](https://img.shields.io/badge/Docker-Enabled-cyan)

## ✨ Fitur Utama
- 📊 **Monitoring Kuota Otomatis**: Memantau penggunaan data (GB) user PPPoE.
- 🔽 **Auto-Throttling**: Otomatis memindahkan user ke profil speed rendah jika limit tercapai.
- 🔄 **Smart Accumulation**: Pemakaian data tetap tersimpan meski user reconnect atau router reboot.
- 👤 **Manajemen User**: Tambah (`/add_user`), Hapus (`/del_user`), dan Kick (`/kick`) user langsung dari Telegram.
- 📱 **Interactive UI**: Tombol interaktif (Inline Keyboard) untuk aksi cepat di pesan status.
- 📅 **Daily Reporting**: Laporan ringkasan harian otomatis setiap pukul 08:00 WIB.
- 💾 **Auto Backup**: Pengiriman file `.db` otomatis ke Telegram setiap tengah malam.

## 🛠️ Persiapan MikroTik
1. Pastikan fitur **API** aktif di MikroTik (`/ip service enable api`).
2. Siapkan dua profil PPPoE:
   - **Normal Profile** (Contoh: `Ilham` - 5M/5M)
   - **Throttled Profile** (Contoh: `LIMIT` - 2M/2M)

## 🚀 Cara Instalasi

1. **Clone Repository**
   ```bash
   git clone https://github.com/username/mikrotik-bot.git
   cd mikrotik-bot
   ```

2. **Konfigurasi Environment**
   Salin file `.env.example` menjadi `.env` dan lengkapi datanya:
   ```bash
   cp .env.example .env
   nano .env
   ```

3. **Jalankan dengan Docker**
   ```bash
   docker-compose up -d --build
   ```

## ⌨️ Daftar Perintah
| Perintah | Deskripsi |
| :--- | :--- |
| `/status [user]` | Cek detail pemakaian & kontrol interaktif |
| `/summary` | Ringkasan traffic jaringan & top usage |
| `/users` | Daftar seluruh user & konfigurasi limit |
| `/sessions` | Lihat user yang sedang online saat ini |
| `/add_user [u p prof]` | Buat user PPPoE baru (Auto Static IP) |
| `/set_limit [u gb]` | Atur limit kuota khusus untuk user tertentu |
| `/health` | Cek status koneksi bot ke MikroTik |

## 🏗️ Arsitektur
Aplikasi ini dibangun menggunakan **Clean Architecture** untuk memastikan kode yang modular dan mudah dikembangkan:
- **Domain**: Inti bisnis dan model data.
- **Application**: Logika proses (Use Cases).
- **Infrastructure**: Implementasi teknis (API MikroTik & SQLite).
- **Interface**: Interaksi luar (Telegram Bot & Workers).

## 📄 Lisensi
Distributed under the MIT License.
