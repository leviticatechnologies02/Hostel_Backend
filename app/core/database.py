from collections.abc import AsyncGenerator
import ssl
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import get_settings

settings = get_settings()

# Configure SSL for asyncpg if not localhost/127.0.0.1
connect_args = {
    "server_settings": {
        "application_name": "leviticanestora_api",
        "statement_timeout": "30000",
        "idle_in_transaction_session_timeout": "60000",
    },
    "timeout": 30,
    "command_timeout": 30,
    "statement_cache_size": 0,  # Required for Supabase Transaction Pooler (pgbouncer)
}

if "localhost" not in settings.database_url and "127.0.0.1" not in settings.database_url:
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ssl_context

# Create engine with OPTIMIZED settings for remote database
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_pre_ping=settings.database_pool_pre_ping,
    pool_recycle=3600,
    connect_args=connect_args
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session."""
    async with AsyncSessionLocal() as session:
        try:
            # Set a timeout for the session
            await session.execute(text("SET statement_timeout = '30000'"))
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()