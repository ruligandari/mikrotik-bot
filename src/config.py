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

    @staticmethod
    def now_local() -> datetime:
        return datetime.now(ZoneInfo(Config.TZ))
    
    @staticmethod
    def month_key() -> str:
        return Config.now_local().strftime('%Y-%m')

    @staticmethod
    def to_gb(bytes_val: int) -> float:
        return round(bytes_val / 1_000_000_000, 2)
