"""REST API ルーター"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc

from app.database import async_session
from app.models import ActivityEvent, Alert, AlertStatus, DailySummary, EventType
from app.services.tapo_monitor import tapo_monitor
from app.services.alert_service import alert_service

router = APIRouter(tags=["api"])
JST = timezone(timedelta(hours=9))


class DashboardSummary(BaseModel):
    is_active: bool
    last_activity_time: Optional[str] = None
    last_activity_device: Optional[str] = None
    today_motion_count: int = 0
    today_plug_count: int = 0
    active_alerts: int = 0
    devices_online: int = 0
    devices_total: int = 0



@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary():
    """ダッシュボードサマリーを取得"""
    now = datetime.now(JST)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session() as session:
        last_event_result = await session.execute(
            select(ActivityEvent).order_by(desc(ActivityEvent.timestamp)).limit(1)
        )
        last_event = last_event_result.scalar_one_or_none()

        is_active = False
        last_time = None
        last_device = None
        if last_event:
            event_time = last_event.timestamp
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=JST)
            elapsed = (now - event_time).total_seconds() / 60
            is_active = elapsed < 30
            last_time = event_time.strftime("%H:%M")
            last_device = last_event.device_name

        motion_result = await session.execute(
            select(func.count(ActivityEvent.id)).where(
                ActivityEvent.timestamp >= today_start,
                ActivityEvent.event_type == EventType.MOTION_DETECTED,
            )
        )
        today_motion = motion_result.scalar() or 0

        plug_result = await session.execute(
            select(func.count(ActivityEvent.id)).where(
                ActivityEvent.timestamp >= today_start,
                ActivityEvent.event_type == EventType.PLUG_ON,
            )
        )
        today_plug = plug_result.scalar() or 0

        alerts_result = await session.execute(
            select(func.count(Alert.id)).where(Alert.status == AlertStatus.TRIGGERED)
        )
        active_alerts = alerts_result.scalar() or 0

    try:
        statuses = await tapo_monitor.get_device_statuses()
        devices_online = sum(1 for s in statuses if s.get("is_online"))
        devices_total = len(statuses)
    except Exception:
        devices_online = 0
        devices_total = 0

    return DashboardSummary(
        is_active=is_active, last_activity_time=last_time,
        last_activity_device=last_device, today_motion_count=today_motion,
        today_plug_count=today_plug, active_alerts=active_alerts,
        devices_online=devices_online, devices_total=devices_total,
    )



@router.get("/events")
async def get_events(limit: int = Query(default=50, le=200), date: Optional[str] = Query(default=None)):
    """活動イベント一覧を取得"""
    async with async_session() as session:
        query = select(ActivityEvent).order_by(desc(ActivityEvent.timestamp))
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=JST)
                next_date = target_date + timedelta(days=1)
                query = query.where(ActivityEvent.timestamp >= target_date, ActivityEvent.timestamp < next_date)
            except ValueError:
                pass
        query = query.limit(limit)
        result = await session.execute(query)
        events = result.scalars().all()

    return [
        {
            "id": e.id,
            "event_type": e.event_type.value if hasattr(e.event_type, 'value') else e.event_type,
            "device_name": e.device_name,
            "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "",
            "details": e.details,
        }
        for e in events
    ]


@router.get("/alerts")
async def get_alerts(status: Optional[str] = Query(default=None), limit: int = Query(default=20, le=100)):
    """アラート一覧を取得"""
    async with async_session() as session:
        query = select(Alert).order_by(desc(Alert.triggered_at))
        if status:
            query = query.where(Alert.status == status)
        query = query.limit(limit)
        result = await session.execute(query)
        alerts = result.scalars().all()

    return [
        {
            "id": a.id,
            "alert_type": a.alert_type.value if hasattr(a.alert_type, 'value') else a.alert_type,
            "status": a.status.value if hasattr(a.status, 'value') else a.status,
            "message": a.message,
            "triggered_at": a.triggered_at.strftime("%Y-%m-%d %H:%M:%S") if a.triggered_at else "",
            "notified": a.notified,
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """アラートを確認済みにする"""
    now = datetime.now(JST)
    async with async_session() as session:
        result = await session.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one_or_none()
        if not alert:
            return {"error": "アラートが見つかりません"}
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = now
        await session.commit()
    return {"status": "ok", "message": "アラートを確認済みにしました"}



@router.get("/devices")
async def get_devices():
    """デバイス状態を取得"""
    try:
        statuses = await tapo_monitor.get_device_statuses()
    except Exception:
        statuses = []
    return [
        {
            "device_name": s["device_name"],
            "device_type": s["device_type"],
            "ip_address": s.get("ip_address"),
            "is_online": s.get("is_online", False),
            "last_seen": s["last_seen"].strftime("%Y-%m-%d %H:%M:%S") if s.get("last_seen") else None,
            "last_event": s.get("last_event"),
        }
        for s in statuses
    ]


@router.get("/daily-summary")
async def get_daily_summaries(days: int = Query(default=7, le=30)):
    """日次サマリーを取得"""
    async with async_session() as session:
        result = await session.execute(
            select(DailySummary).order_by(desc(DailySummary.date)).limit(days)
        )
        summaries = result.scalars().all()
    return [
        {
            "date": s.date,
            "first_activity_time": s.first_activity_time.strftime("%H:%M") if s.first_activity_time else None,
            "last_activity_time": s.last_activity_time.strftime("%H:%M") if s.last_activity_time else None,
            "motion_count": s.motion_count,
            "plug_on_count": s.plug_on_count,
            "max_inactivity_minutes": s.max_inactivity_minutes,
            "alerts_triggered": s.alerts_triggered,
        }
        for s in summaries
    ]


@router.get("/timeline")
async def get_timeline(date: Optional[str] = Query(default=None)):
    """時系列タイムラインデータを取得（24時間を1時間ごとに区切り）"""
    now = datetime.now(JST)
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=JST)
        except ValueError:
            target_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        target_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    timeline = []
    for hour in range(24):
        slot_start = target_date.replace(hour=hour)
        slot_end = slot_start + timedelta(hours=1)

        async with async_session() as session:
            motion_result = await session.execute(
                select(func.count(ActivityEvent.id)).where(
                    ActivityEvent.timestamp >= slot_start,
                    ActivityEvent.timestamp < slot_end,
                    ActivityEvent.event_type == EventType.MOTION_DETECTED,
                )
            )
            motion_count = motion_result.scalar() or 0

            plug_result = await session.execute(
                select(func.count(ActivityEvent.id)).where(
                    ActivityEvent.timestamp >= slot_start,
                    ActivityEvent.timestamp < slot_end,
                    ActivityEvent.event_type.in_([EventType.PLUG_ON, EventType.PLUG_OFF]),
                )
            )
            plug_count = plug_result.scalar() or 0

        timeline.append({
            "hour": hour, "label": f"{hour:02d}:00",
            "motion_count": motion_count, "plug_count": plug_count,
            "total": motion_count + plug_count,
        })

    return {"date": target_date.strftime("%Y-%m-%d"), "timeline": timeline}
