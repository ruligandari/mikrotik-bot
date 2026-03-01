from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional

from src.config import Config
from src.application.fup_service import FupService
from src.application.admin_service import AdminService
from src.application.billing_service import BillingService
from src.interface.api.security import create_access_token, get_current_user, verify_password, get_password_hash

class Token(BaseModel):
    access_token: str
    token_type: str

class UserAddRequest(BaseModel):
    username: str
    password: str
    profile: str
    whatsapp: Optional[str] = None

class UserUpdateRequest(BaseModel):
    username: str
    whatsapp: Optional[str] = None

class PaymentRequest(BaseModel):
    username: str
    amount: float

class LimitRequest(BaseModel):
    username: str
    limit_gb: float

class ToggleRequest(BaseModel):
    username: str
    enabled: bool

class AdminUpdateRequest(BaseModel):
    new_username: Optional[str] = None
    new_password: Optional[str] = None

def create_router(fup_service: FupService, admin_service: AdminService, billing_service: BillingService):
    router = APIRouter(prefix="/api/v1")

    # --- Public Auth ---
    @router.post("/auth/login", response_model=Token)
    async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
        # 1. Get credentials from DB
        db_user = admin_service.repo.get_setting("admin_username", "admin")
        db_pwd_hash = admin_service.repo.get_setting("admin_password_hash")
        
        # 2. Verify
        if db_pwd_hash:
            # Login via DB (already hashed)
            is_valid = (form_data.username == db_user and verify_password(form_data.password, db_pwd_hash))
        else:
            # Fallback to .env (admin_password_hash not set yet)
            is_valid = (form_data.username == "admin" and form_data.password == Config.ADMIN_PASSWORD)

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=Config.JWT_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": form_data.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}

    @router.post("/auth/update-admin", dependencies=[Depends(get_current_user)])
    async def update_admin(req: AdminUpdateRequest):
        if req.new_username:
            admin_service.repo.set_setting("admin_username", req.new_username)
        if req.new_password:
            hashed = get_password_hash(req.new_password)
            admin_service.repo.set_setting("admin_password_hash", hashed)
        return {"message": "Admin credentials updated. Silakan login kembali dengan data baru."}

    # --- Protected Routes ---
    
    @router.get("/health", dependencies=[Depends(get_current_user)])
    async def health():
        return {"status": "ok", "version": "7.2"}

    @router.get("/summary", dependencies=[Depends(get_current_user)])
    async def get_summary():
        total, top = admin_service.get_summary_data()
        return {
            "month": Config.month_key(),
            "total_usage_gb": Config.to_gb(total),
            "top_users": [{"username": u, "usage_gb": Config.to_gb(b)} for u, b in top]
        }

    @router.get("/users", dependencies=[Depends(get_current_user)])
    async def list_users():
        users = admin_service.repo.get_all_users_config()
        return [
            {
                "username": u,
                "enabled": bool(e),
                "threshold_gb": t if t else Config.FUP_THRESHOLD_GB,
                "profile": p,
                "package_name": Config.get_package_info(p)['name'],
                "whatsapp": wa
            } for u, e, t, p, wa in users
        ]

    @router.get("/status/{username}", dependencies=[Depends(get_current_user)])
    async def get_user_status(username: str):
        mk = Config.month_key()
        bt = admin_service.repo.get_accumulated_bytes(mk, username)
        enabled, threshold = admin_service.repo.get_user_config(username)
        profile = admin_service.repo.get_user_profile(username)
        state_obj = admin_service.repo.get_user_state(username)
        pkg_info = Config.get_package_info(profile)
        wa = admin_service.repo.get_user_whatsapp(username)
        
        # MikroTik Dynamic Data
        mk_secret = admin_service.mk_gateway.get_ppp_secret_details(username)
        remote_address = mk_secret.get('remote-address') if mk_secret else "N/A"
        
        return {
            "username": username,
            "usage_gb": Config.to_gb(bt),
            "threshold_gb": threshold,
            "enabled": enabled,
            "profile": profile,
            "package_name": pkg_info['name'],
            "price": pkg_info['price'],
            "whatsapp": wa,
            "remote_address": remote_address,
            "state": state_obj.state if state_obj else "normal",
            "last_action": state_obj.last_action_at if state_obj else None
        }

    @router.get("/sessions", dependencies=[Depends(get_current_user)])
    async def get_active_sessions():
        actives = admin_service.fetch_active_sessions()
        return actives

    @router.get("/profiles", dependencies=[Depends(get_current_user)])
    async def get_profiles():
        profiles = admin_service.get_ppp_profiles()
        result = []
        for p in profiles:
            pname = p.get("name")
            pkg_info = Config.get_package_info(pname)
            result.append({
                "profile": pname,
                "package_name": pkg_info['name'],
                "price": pkg_info['price'],
                "local_address": p.get("local-address"),
                "remote_address": p.get("remote-address")
            })
        return result

    @router.get("/throttled", dependencies=[Depends(get_current_user)])
    async def get_throttled_users():
        mk = Config.month_key()
        users = admin_service.repo.get_throttled_users(mk)
        return [{"username": u, "ts": ts, "reason": r} for u, ts, r in users]

    @router.get("/logs/{username}", dependencies=[Depends(get_current_user)])
    async def get_user_logs(username: str, limit: int = 10):
        logs = admin_service.repo.get_action_logs(username, limit=limit)
        return [{"ts": ts, "action": a, "detail": d} for ts, a, d in logs]

    # --- Billing Endpoints ---
    
    @router.post("/billing/record-payment", dependencies=[Depends(get_current_user)])
    async def record_payment(req: PaymentRequest):
        success, msg = billing_service.process_payment(req.username, req.amount)
        if not success:
            raise HTTPException(status_code=500, detail=msg)
        return {"message": msg}

    @router.get("/billing/status/{username}", dependencies=[Depends(get_current_user)])
    async def get_billing_status(username: str):
        mk = Config.month_key()
        status = admin_service.repo.get_billing_status(username, mk)
        if not status:
            return {"username": username, "month": mk, "is_paid": False, "amount_paid": 0}
        
        is_paid, amount, ts = status
        return {
            "username": username,
            "month": mk,
            "is_paid": is_paid,
            "amount_paid": amount,
            "updated_at": ts
        }

    @router.get("/billing/unpaid", dependencies=[Depends(get_current_user)])
    async def get_unpaid_users():
        mk = Config.month_key()
        unpaid_data = admin_service.repo.get_unpaid_with_profile(mk)
        result = []
        total_piutang = 0
        for uname, profile in unpaid_data:
            price = Config.get_package_price(profile)
            total_piutang += price
            result.append({"username": uname, "profile": profile or "NORMAL", "price": price})
        
        return {
            "month": mk, 
            "unpaid_count": len(unpaid_data), 
            "total_piutang": total_piutang,
            "users": result
        }

    # --- Admin Actions ---

    @router.post("/user/add", dependencies=[Depends(get_current_user)])
    async def add_user(req: UserAddRequest):
        success, ip, err = admin_service.add_user(req.username, req.password, req.profile, req.whatsapp)
        if not success:
            raise HTTPException(status_code=500, detail=err)
            
        return {"message": f"User {req.username} created", "ip": ip}

    @router.post("/user/update", dependencies=[Depends(get_current_user)])
    async def update_user(req: UserUpdateRequest):
        # Current data for COALESCE-like behavior or manual get
        profile = admin_service.repo.get_user_profile(req.username)
        admin_service.repo.register_user(req.username, req.username, f"<pppoe-{req.username}>", profile, req.whatsapp)
        return {"message": f"User {req.username} updated"}

    @router.delete("/user/{username}", dependencies=[Depends(get_current_user)])
    async def delete_user(username: str):
        success, err = admin_service.delete_user(username)
        if not success:
            raise HTTPException(status_code=500, detail=err)
        return {"message": f"User {username} deleted"}

    @router.post("/user/kick/{username}", dependencies=[Depends(get_current_user)])
    async def kick_user(username: str):
        success, err = admin_service.kick_user(username)
        if not success:
            raise HTTPException(status_code=500, detail=err)
        return {"message": f"User {username} kicked successfully"}

    @router.post("/user/set-limit", dependencies=[Depends(get_current_user)])
    async def set_limit(req: LimitRequest):
        admin_service.update_user_limit(req.username, req.limit_gb)
        return {"message": f"Limit for {req.username} set to {req.limit_gb} GB"}

    @router.post("/user/toggle-fup", dependencies=[Depends(get_current_user)])
    async def toggle_fup(req: ToggleRequest):
        admin_service.toggle_user_fup(req.username, req.enabled)
        return {"message": f"Auto-FUP for {req.username} enabled: {req.enabled}"}

    @router.post("/user/force-throttle/{username}", dependencies=[Depends(get_current_user)])
    async def force_throttle(username: str):
        success, err = admin_service.mk_gateway.set_pppoe_profile(username, Config.THROTTLE_RATE)
        if success:
            admin_service.kick_user(username)
            admin_service.repo.save_user_state(
                admin_service.repo.get_user_state(username) or 
                admin_service.repo.save_user_state( # Placeholder if none
                    admin_service.repo.get_user_state(username) # Just use existing logic
                )
            )
            # Simplest for now: mirror bot.py force logic
            from src.domain.models import UserState
            admin_service.repo.save_user_state(UserState(username, Config.month_key(), 'throttled', Config.now_local().isoformat(), "Manual force throttle via API"))
            return {"message": f"{username} throttled"}
        raise HTTPException(status_code=500, detail=err)

    @router.post("/user/force-normal/{username}", dependencies=[Depends(get_current_user)])
    async def force_normal(username: str):
        success, err = admin_service.mk_gateway.set_pppoe_profile(username, Config.BASE_RATE)
        if success:
            admin_service.kick_user(username)
            from src.domain.models import UserState
            admin_service.repo.save_user_state(UserState(username, Config.month_key(), 'normal', Config.now_local().isoformat(), "Manual force normal via API"))
            return {"message": f"{username} set to normal"}
        raise HTTPException(status_code=500, detail=err)

    @router.post("/check-now", dependencies=[Depends(get_current_user)])
    async def run_check():
        notifs = fup_service.run_fup_cycle()
        return {"messages": notifs}

    return router
