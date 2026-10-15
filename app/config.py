from functools import lru_cache
from typing import List, Optional
import re
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Levitica Nestora API"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    
    # Database configuration with Render support
    database_url: str = Field(
        default="postgresql+asyncpg://leviticanestora_db_0hw4_user:0L7DvsoMZ4ff88BYqohgiceUJITTSmJG@dpg-d7kaci4m0tmc73aeivm0-a.oregon-postgres.render.com:5432/leviticanestora_db_0hw4"
    )

    # Redis configuration
    redis_url: str = "redis://localhost:6379/0"
    
    # Database pool settings for production
    database_pool_size: int = Field(default=5, description="Database connection pool size")
    database_max_overflow: int = Field(default=10, description="Max overflow connections")
    database_pool_timeout: int = Field(default=30, description="Connection timeout in seconds")
    database_pool_pre_ping: bool = Field(default=True, description="Verify connections before using")
    
    # Security
    secret_key: str = "change-me-in-production-use-environment-variable"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174", 
        "http://localhost:3000",
        "http://localhost:50231",
        "https://hma-theta.vercel.app",
        "https://hostelproject-eta.vercel.app",
        "https://www.leviticanestora.com",
        "https://leviticanestora.com",
    ]

    # httpOnly refresh cookie settings
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_samesite: str = "lax"
    refresh_cookie_path: str = "/"
    
    # Razorpay
    razorpay_key_id: str = "rzp_live_T1totnHl5LEoTG"
    razorpay_key_secret: str = "cWjz2stqI2MsZ3LPQydlZh6F"
    razorpay_webhook_secret: str = "cWjz2stqI2MsZ3LPQydlZh6F"

    # Encryption key for storing sensitive values (Razorpay secrets) in the DB
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = Field(default="", description="Fernet encryption key for securing stored secrets")

    # Google Gemini AI Key for Nestora Assistant
    gemini_api_key: str = Field(default="", description="Google Gemini API Key for Chat Assistant")


    # 2Factor SMS OTP
    two_factor_api_key: str = Field(default="", description="2Factor.in Message API Key for SMS OTP")

    
    # OTP
    otp_expiry_minutes: int = 10
    otp_max_attempts: int = 5
    
    # Email Configuration
    contact_owner_email: str = Field(default="hemantpawade48@gmail.com", description="SaaS Owner email for contact notifications")
    email_provider: str = Field(default="smtp", description="Email provider: smtp or brevo")
    brevo_api_key: str = Field(default="", description="Brevo API Key")
    brevo_sender_email: str = Field(default="", description="Brevo Sender Email")
    email_send_timeout: int = Field(default=10, description="Email send timeout in seconds")
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str = Field(default="", description="SMTP username")
    smtp_password: str = Field(default="", description="SMTP password")
    email_from: str = Field(default="noreply@leviticanestora.com", description="From email address")
    
    # AWS S3 Configuration
    aws_access_key_id: str = Field(default="", description="AWS access key ID")
    aws_secret_access_key: str = Field(default="", description="AWS secret access key")
    aws_storage_bucket_name: str = Field(default="leviticanestora-uploads", description="S3 bucket name")
    aws_region: str = Field(default="ap-south-1", description="AWS region")

    # Cloudinary Configuration
    cloudinary_cloud_name: str = Field(default="", description="Cloudinary cloud name")
    cloudinary_api_key: str = Field(default="", description="Cloudinary API key")
    cloudinary_api_secret: str = Field(default="", description="Cloudinary API secret")

    @field_validator("database_url", mode="before")
    @classmethod
    def clean_database_url(cls, v: str) -> str:
        """Remove any SSL parameters from URL - they're handled via connect_args"""
        if v:
            # Remove any sslmode or ssl parameters
            v = re.sub(r'\?sslmode=[^&]+', '', v)
            v = re.sub(r'&sslmode=[^&]+', '', v)
            v = re.sub(r'\?ssl=[^&]+', '', v)
            v = re.sub(r'&ssl=[^&]+', '', v)
            v = re.sub(r'[?&]$', '', v)
        return v
    
    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Ensure database URL has asyncpg driver and handles Render's postgres:// scheme"""
        if value:
            if value.startswith("postgres://"):
                value = value.replace("postgres://", "postgresql+asyncpg://", 1)
            elif value.startswith("postgresql://") and "+asyncpg" not in value:
                value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value
    
    def get_sync_database_url(self) -> str:
        """Get sync database URL for Alembic and scripts"""
        url = self.database_url
        if "+asyncpg" in url:
            url = url.replace("+asyncpg", "")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()