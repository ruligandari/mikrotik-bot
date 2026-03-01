import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load environment variables from the project root
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

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
        'limit': 30000.0,
        'normal': 100000.0
    }

    @classmethod
    def get_package_price(cls, profile: str) -> float:
        if not profile:
            return cls.BILLING_MONTHLY_PRICE
        return cls.PACKAGES.get(profile.lower(), cls.BILLING_MONTHLY_PRICE)
    
    API_PORT = int(os.getenv('API_PORT', '8000'))
    # Default to common development origins if * is used with credentials
    cors_raw = os.getenv('API_CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173')
    if cors_raw == '*':
        API_CORS_ORIGINS = ['http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:5173']
    else:
        API_CORS_ORIGINS = [orig.strip() for orig in cors_raw.split(',')]
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
