"""データベース接続・セッション管理モジュール"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# 非同期エンジン作成
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

# 非同期セッションファクトリ
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy ベースクラス"""
    pass


async def init_db():
    """データベース初期化（テーブル作成）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI依存性注入用のDBセッション取得"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
