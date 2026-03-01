from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional

from src.config import Config
from src.application.fup_service import FupService
from src.application.admin_service import AdminService
from src.application.billing_service import BillingService
from src.interface.api.security import create_access_token, get_current_user

class Token(BaseModel):
    access_token: str
    token_type: str

class UserAddRequest(BaseModel):
    username: str
    password: str
    profile: str

class PaymentRequest(BaseModel):
    username: str
    amount: float

class LimitRequest(BaseModel):
    username: str
    limit_gb: float

class ToggleRequest(BaseModel):
    username: str
    enabled: bool

def create_router(fup_service: FupService, admin_service: AdminService, billing_service: BillingService):
    router = APIRouter(prefix="/api/v1")

    # --- Public Auth ---
    @router.post("/auth/login", response_model=Token)
    async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
        # Simple admin password check
        if form_data.username != "admin" or form_data.password != Config.ADMIN_PASSWORD:
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
                "threshold_gb": t if t else Config.FUP_THRESHOLD_GB
            } for u, e, t in users
        ]

    @router.get("/status/{username}", dependencies=[Depends(get_current_user)])
    async def get_user_status(username: str):
        mk = Config.month_key()
        bt = admin_service.repo.get_accumulated_bytes(mk, username)
        enabled, threshold = admin_service.repo.get_user_config(username)
        state_obj = admin_service.repo.get_user_state(username)
        
        return {
            "username": username,
            "usage_gb": Config.to_gb(bt),
            "threshold_gb": threshold,
            "enabled": enabled,
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
        return [{"name": p.get("name"), "local-address": p.get("local-address"), "remote-address": p.get("remote-address")} for p in profiles]

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
            price = Config.PACKAGES.get(profile, Config.BILLING_MONTHLY_PRICE)
            total_piutang += price
            result.append({"username": uname, "profile": profile, "price": price})
        
        return {
            "month": mk, 
            "unpaid_count": len(unpaid_data), 
            "total_piutang": total_piutang,
            "users": result
        }

    # --- Admin Actions ---

    @router.post("/user/add", dependencies=[Depends(get_current_user)])
    async def add_user(req: UserAddRequest):
        success, ip, err = admin_service.add_user(req.username, req.password, req.profile)
        if not success:
            raise HTTPException(status_code=500, detail=err)
        return {"message": f"User {req.username} created", "ip": ip}

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
