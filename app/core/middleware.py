from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


def register_middleware(app: FastAPI) -> None:
    settings = get_settings()
    
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://localhost:8000",
        "https://hma-theta.vercel.app",
        "https://hostelproject-eta.vercel.app",
        "https://www.leviticanestora.com",
        "https://leviticanestora.com",
    ]
    
    if settings.cors_origins:
        allowed_origins.extend(settings.cors_origins)
    
    unique_origins = []
    for origin in allowed_origins:
        if origin not in unique_origins and "*" not in origin:
            unique_origins.append(origin)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=unique_origins,
        allow_origin_regex=r"^(https://.*\.vercel\.app|http://localhost:\d+|http://127\.0\.0\.1:\d+)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    
    print(f"CORS Middleware registered with origins: {unique_origins if settings.app_env != 'development' else ['*']}")