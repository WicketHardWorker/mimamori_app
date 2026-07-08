"""MiMaMoRi - 見守りアプリ メインエントリポイント"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import dashboard, api
from app.scheduler.jobs import setup_scheduler, shutdown_scheduler
from app.services.tapo_monitor import tapo_monitor
from app.services.line_notify import line_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    logger.info("=" * 50)
    logger.info("🏠 MiMaMoRi 見守りアプリを起動します...")
    logger.info("=" * 50)

    await init_db()
    logger.info("✅ データベースを初期化しました")

    await line_service.initialize()

    try:
        await tapo_monitor.initialize()
    except Exception as e:
        logger.warning(f"⚠️ Tapoデバイスへの接続に失敗しました: {e}")

    setup_scheduler()
    logger.info(f"🌐 Web ダッシュボード: http://localhost:{settings.port}")
    logger.info("=" * 50)

    yield

    logger.info("MiMaMoRi を終了します...")
    shutdown_scheduler()
    await tapo_monitor.close()
    await line_service.close()
    logger.info("正常に終了しました")


app = FastAPI(
    title="MiMaMoRi - 見守りアプリ",
    description="TP-Link Tapoデバイスを使った一人暮らしの親の見守りシステム",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(settings.base_dir / "app" / "static")), name="static")
app.include_router(dashboard.router)
app.include_router(api.router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)
