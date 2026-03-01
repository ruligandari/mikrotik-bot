from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class User:
    username: str
    pppoe_name: str
    queue_name: str
    enabled: bool = True
    threshold_gb: Optional[float] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class Usage:
    month_key: str
    username: str
    bytes_in: int = 0
    bytes_out: int = 0
    bytes_total: int = 0
    last_sample_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class UserState:
    username: str
    month_key: str
    state: str = 'normal'  # 'normal' or 'throttled'
    last_action_at: Optional[str] = None
    last_reason: Optional[str] = None

@dataclass
class Payment:
    username: str
    month_key: str  # YYYY-MM
    amount: float
    paid_at: str
    method: str = 'manual'
    id: Optional[int] = None

@dataclass
class BillState:
    username: str
    month_key: str
    is_paid: bool = False
    due_at: Optional[str] = None

@dataclass
class ActionLog:
    username: str
    action: str
    detail: str = ""
    ts: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None
