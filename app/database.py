from collections.abc import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from app.config import settings

logger = structlog.get_logger()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(MappedAsDataclass, DeclarativeBase):
    pass


_bg_engine: AsyncEngine | None = None
_bg_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_background_session_factory() -> async_sessionmaker[AsyncSession]:
    global _bg_engine, _bg_session_factory
    if _bg_engine is None:
        _bg_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.SQL_ECHO,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
        )
        _bg_session_factory = async_sessionmaker(
            _bg_engine, class_=AsyncSession, expire_on_commit=False,
        )
    return _bg_session_factory


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            logger.error("session_rollback", error=str(exc), exc_info=True)
            await session.rollback()
            raise
