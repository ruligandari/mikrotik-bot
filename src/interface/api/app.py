from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import Config
from src.application.fup_service import FupService
from src.application.admin_service import AdminService
from src.interface.api.routes import create_router

def create_app(fup_service: FupService, admin_service: AdminService) -> FastAPI:
    # Disable docs in production
    show_docs = Config.ENVIRONMENT == 'development'
    
    app = FastAPI(
        title="MikroTik Pro Manager API",
        version="1.1.0",
        description="Backend API for MikroTik FUP Dashboard (Full JWT)",
        docs_url="/docs" if show_docs else None,
        redoc_url="/redoc" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Config.API_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include Routes
    router = create_router(fup_service, admin_service)
    app.include_router(router)

    return app
