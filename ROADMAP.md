# 🚀 Future Roadmap: MikroTik FUP Manager

Dokumen ini mencatat ide pengembangan fitur untuk fase selanjutnya sesuai hasil diskusi. Fitur-fitur ini diparkir sementara dan akan diimplementasikan saat dibutuhkan di lapangan.

## 💳 1. Sistem Billing & Isolir Otomatis (Priority: High)
Menambahkan modul penagihan untuk mengelola masa aktif pelanggan secara otomatis.

### Fitur Utama:
- **Subscription Management**: Setiap user memiliki atribut `expiry_date`.
- **Auto-Disable (Isolir)**: Bot otomatis menonaktifkan (*disable*) secret PPPoE jika melewati jatuh tempo tanpa pembayaran.
- **Payment Record**: Mencatat riwayat pembayaran bulanan (Lunas/Hutang).
- **Payment Reminders**: Notifikasi otomatis via Telegram H-3 sebelum masa aktif habis.

### Komponen Teknis:
- **Service Layer**: `BillingService.py` untuk logika perpanjangan dan masa aktif.
- **Repository**: Tabel baru `subscriptions` dan `payments`.
- **Gateway**: Integrasi Payment Gateway (QRIS/VA) jika ingin otomatisasi penuh.

## 👥 2. Multi-Role Interface (Admin vs Customer)
- **Admin Bot**: Tetap seperti sekarang (Full Control).
- **Customer Bot**: User bisa mengetik `/cek_kuota` atau `/bayar` untuk akun mereka sendiri.
- **Login System**: Verifikasi nomor HP atau User PPPoE via bot.

## 📈 3. Monitoring & Analytics (Dashboard)
- Grafik penggunaan bandwidth harian/mingguan.
- Prediksi kapan kuota user akan habis berdasarkan tren pemakaian.
- Laporan pendapatan bulanan (jika Billing sudah aktif).

---

> [!NOTE]
> Fitur ini saat ini berstatus **BACKLOG** (Disimpan untuk update mendatang).
