from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class User:
    username: str
    pppoe_name: str
    queue_name: str
    enabled: bool = True
    threshold_gb: Optional[float] = None
    updated_at: Optional[str] = None

@dataclass
class Usage:
    month_key: str
    username: str
    bytes_in: int = 0
    bytes_out: int = 0
    bytes_total: int = 0
    last_raw_total: int = 0
    last_sample_at: Optional[str] = None

@dataclass
class UserState:
    username: str
    month_key: str
    state: str = 'normal'
    last_action_at: Optional[str] = None
    last_reason: Optional[str] = None

@dataclass
class ActionLog:
    id: Optional[int] = None
    ts: str = field(default_factory=lambda: datetime.now().isoformat())
    username: str = ""
    action: str = ""
    detail: str = ""
