import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load specifically from the same location as before
load_dotenv('/app/.env')

class Config:
    # MikroTik
    MIKROTIK_HOST = os.getenv('MIKROTIK_HOST', '').strip()
    MIKROTIK_PORT = int(os.getenv('MIKROTIK_PORT', '8728'))
    MIKROTIK_USER = os.getenv('MIKROTIK_USER', '').strip()
    MIKROTIK_PASS = os.getenv('MIKROTIK_PASS', '').strip()
    MIKROTIK_USE_SSL = os.getenv('MIKROTIK_USE_SSL', 'false').lower() == 'true'
    
    # Telegram
    BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
    ADMIN_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    
    # Application
    TZ = os.getenv('TZ', 'Asia/Jakarta')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL_SECONDS', '300'))
    FUP_THRESHOLD_GB = float(os.getenv('FUP_THRESHOLD_GB', '100'))
    BASE_RATE = os.getenv('BASE_RATE', 'Ilham')
    THROTTLE_RATE = os.getenv('THROTTLE_RATE', 'LIMIT')
    
    # Database
    DB_PATH = '/app/data/bot.db'
    
    # Billing
    BILLING_DUE_DAY = int(os.getenv('BILLING_DUE_DAY', '20'))
    BILLING_MONTHLY_PRICE = float(os.getenv('BILLING_MONTHLY_PRICE', '150000')) # Global default
    
    # Package Definitions (Profile Name -> Price)
    PACKAGES = {
        'ilham': 50000.0,
        'LIMIT': 30000.0,
        'NORMAL': 100000.0 # Contoh default lain
    }
    
    # API
    API_PORT = int(os.getenv('API_PORT', '8000'))
    API_CORS_ORIGINS = os.getenv('API_CORS_ORIGINS', '*').split(',')
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development').lower()
    
    # JWT Security
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'default_secret_dont_use_in_prod')
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '1440'))
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

    @staticmethod
    def now_local() -> datetime:
        return datetime.now(ZoneInfo(Config.TZ))
    
    @staticmethod
    def month_key() -> str:
        return Config.now_local().strftime('%Y-%m')

    @staticmethod
    def to_gb(bytes_val: int) -> float:
        return round(bytes_val / 1_000_000_000, 2)
