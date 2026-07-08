"""ダッシュボード画面のルーター"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings

router = APIRouter(tags=["dashboard"])

templates = Jinja2Templates(directory=str(settings.base_dir / "app" / "templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """メインダッシュボード画面"""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "MiMaMoRi - 見守りダッシュボード"},
    )
