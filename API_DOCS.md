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
Mendapatkan daftar semua user yang terdaftar beserta konfigurasi limitnya.
*   **Endpoint:** `GET /api/v1/users`
*   **Response:**
    ```json
    [
      {
        "username": "user1",
        "enabled": true,
        "threshold_gb": 100.0
      }
    ]
    ```

### 4. Get User Detail Status
Mendapatkan detail pemakaian real-time dan state FUP user tertentu.
*   **Endpoint:** `GET /api/v1/status/{username}`
*   **Response:**
    ```json
    {
      "username": "user1",
      "usage_gb": 85.5,
      "threshold_gb": 100.0,
      "enabled": true,
      "state": "normal",
      "last_action": "2026-03-01T10:00:00"
    }
    ```

### 5. Get Active Sessions
Melihat siapa saja yang saat ini terkoneksi (PPPoE Active).
*   **Endpoint:** `GET /api/v1/sessions`

### 6. Get Throttled Users
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
      "profile": "NORMAL"
    }
    ```

### 9. Delete User
Menghapus user dari MikroTik dan Database.
*   **Endpoint:** `DELETE /api/v1/user/{username}`

### 10. Set Quota Limit
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

## 💡 Tips untuk AI Dashboard Builder
- Gunakan **Axios** atau **Fetch API** dengan *Interceptor* untuk menambahkan header `Authorization: Bearer <token>` secara otomatis.
- Token JWT bapak berlaku selama 24 jam (`1440` menit) sesuai konfigurasi `.env`.
- Base URL API: `http://<ip_server_bapak>:8000`
