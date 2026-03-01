# 📖 API Documentation: MikroTik Pro Manager (v7.2)

Dokumen ini berisi referensi lengkap API untuk digunakan sebagai panduan pembuatan **Dashboard Web**. API ini menggunakan standar **RESTful** dengan format pertukaran data **JSON** dan keamanan berbasis **JWT (Bearer Token)**.

## 🔓 Keamanan & Autentikasi
API ini dilindungi dengan **JWT Authentication**. Semua endpoint (kecuali Login) mewajibkan header: 
`Authorization: Bearer <your_access_token>`

### 1. Login (Mendapatkan Token)
*   **Endpoint:** `POST /api/v1/auth/login`
*   **Content-Type:** `application/x-www-form-urlencoded`
*   **Body Parameter:**
    *   `username`: (Default: `admin`)
    *   `password`: (Sesuai `ADMIN_PASSWORD` di `.env`)
*   **Success Response (200 OK):**
    ```json
    {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "token_type": "bearer"
    }
    ```

---

## 📊 Endpoints Monitoring (Data Retrieval)

### 2. Get Network Summary
Mendapatkan statistik total traffic jaringan dan Top 5 pengguna bulan ini.
*   **Endpoint:** `GET /api/v1/summary`
*   **Response:**
    ```json
    {
      "month": "2026-03",
      "total_usage_gb": 150.5,
      "top_users": [
        {"username": "user1", "usage_gb": 45.2},
        {"username": "user2", "usage_gb": 30.1}
      ]
    }
    ```

### 3. List All Users
Mendapatkan daftar semua user yang terdaftar beserta konfigurasi limit dan paketnya.
*   **Endpoint:** `GET /api/v1/users`
*   **Response:**
    ```json
    [
      {
        "username": "user1",
        "enabled": true,
        "threshold_gb": 100.0,
        "profile": "Ilham",
        "package_name": "Paket 5Mbps",
        "whatsapp": "08123456789"
      }
    ]
    ```

### 4. Get User Detail Status
Mendapatkan detail pemakaian real-time, paket, dan state FUP user tertentu.
*   **Endpoint:** `GET /api/v1/status/{username}`
*   **Response:**
    ```json
    {
      "username": "user1",
      "usage_gb": 85.5,
      "threshold_gb": 100.0,
      "enabled": true,
      "profile": "Ilham",
      "package_name": "Paket 5Mbps",
      "price": 50000.0,
      "whatsapp": "08123456789",
      "remote_address": "192.168.10.50",
      "state": "normal",
      "last_action": "2026-03-01T10:00:00"
    }
    ```

### 5. Get Active Sessions
Melihat siapa saja yang saat ini terkoneksi (PPPoE Active).
*   **Endpoint:** `GET /api/v1/sessions`

### 6. Get PPP Profiles
Melihat daftar profile PPPoE yang tersedia di MikroTik (berguna untuk dropdown Add User di UI).
*   **Endpoint:** `GET /api/v1/profiles`
*   **Response:**
    ```json
    [
      {
       "price": 50000.0,
        "local_address": "192.168.10.1",
        "remote_address": null
      },
      {
        "profile": "LIMIT",
        "package_name": "Paket Lite",
        "price": 30000.0,
        "local_address": "192.168.10.1",
        "remote_address": null
      }
    ]
    ``` "profile": "Ilham",
        "package_name": "Paket 5Mbps",
        

### 7. Get Throttled Users
Daftar user yang saat ini sedang dalam status limit kecepatan.
*   **Endpoint:** `GET /api/v1/throttled`

### 7. Get Action Logs
Melihat riwayat aksi sistem (throttle, unthrottle, add, dsb) untuk user tertentu.
*   **Endpoint:** `GET /api/v1/logs/{username}?limit=10`

---

## ⚙️ Endpoints Management (Actions)

### 8. Add PPPoE User
Membuat user baru di MikroTik (Auto IP Static Allocation).
*   **Endpoint:** `POST /api/v1/user/add`
*   **Body (JSON):**
    ```json
    {
      "username": "user_baru",
      "password": "password123",
      "profile": "NORMAL",
      "whatsapp": "08123456789"
    }
    ```

### 10. Update User Data
Update informasi user (seperti nomor WhatsApp).
*   **Endpoint:** `POST /api/v1/user/update`
*   **Body (JSON):**
    ```json
    {
      "username": "user1",
      "whatsapp": "08987654321"
    }
    ```

### 11. Delete User
Menghapus user dari MikroTik dan Database.
*   **Endpoint:** `DELETE /api/v1/user/{username}`

### 12. Set Quota Limit
Mengatur limit GB khusus untuk user tertentu.
*   **Endpoint:** `POST /api/v1/user/set-limit`
*   **Body (JSON):**
    ```json
    {
      "username": "user1",
      "limit_gb": 150.0
    }
    ```

### 11. Kick User
Memutus koneksi aktif user secara paksa.
*   **Endpoint:** `POST /api/v1/user/kick/{username}`

### 12. Toggle FUP Monitoring
Mengaktifkan atau mematikan sistem auto-throttle untuk user tertentu.
*   **Endpoint:** `POST /api/v1/user/toggle-fup`
*   **Body (JSON):**
    ```json
    {
      "username": "user1",
      "enabled": false
    }
    ```

### 13. Force Throttle / Normal
Memaksa user masuk ke status limit atau normal secara manual.
*   **Endpoint:** `POST /api/v1/user/force-throttle/{username}`
*   **Endpoint:** `POST /api/v1/user/force-normal/{username}`

---

### 13. Force Throttle / Normal
*   **Endpoint:** `POST /api/v1/user/force-throttle/{username}`
*   **Endpoint:** `POST /api/v1/user/force-normal/{username}`

---

## 💰 Endpoints Billing (Payments)

### 14. Record Payment
Mencatat pembayaran manual dan otomatis mengaktifkan internet (jika sebelumnya terisolir).
*   **Endpoint:** `POST /api/v1/billing/record-payment`
*   **Body (JSON):**
    ```json
    {
      "username": "user1",
      "amount": 150000.0
    }
    ```

### 15. Get Billing Status
Cek apakah user tertentu sudah bayar di bulan berjalan.
*   **Endpoint:** `GET /api/v1/billing/status/{username}`
*   **Response:**
    ```json
    {
      "username": "user1",
      "month": "2026-03",
      "is_paid": true,
      "amount_paid": 150000.0,
      "updated_at": "2026-03-05T10:00:00"
    }
    ```

### 16. List Unpaid Users
Daftar penunggak yang belum lunas di bulan berjalan beserta total tagihan yang menggantung.
*   **Endpoint:** `GET /api/v1/billing/unpaid`
*   **Response:**
    ```json
    {
      "month": "2026-03",
      "unpaid_count": 2,
      "total_piutang": 80000.0,
      "users": [
        {"username": "user2", "profile": "LIMIT", "price": 30000.0},
        {"username": "user3", "profile": "Ilham", "price": 50000.0}
      ]
    }
    ```

---

## 💡 Tips untuk AI Dashboard Builder
- Gunakan **Axios** atau **Fetch API** dengan *Interceptor* untuk menambahkan header `Authorization: Bearer <token>` secara otomatis.
- Token JWT bapak berlaku selama 24 jam (`1440` menit) sesuai konfigurasi `.env`.
- Base URL API: `http://<ip_server_bapak>:8000`
