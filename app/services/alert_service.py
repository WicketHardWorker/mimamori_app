"""アラート判定サービス

活動データを分析し、異常を検知した場合にアラートを発火する。
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import ActivityEvent, Alert, AlertType, AlertStatus, DailySummary, EventType
from app.services.line_notify import line_service

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


class AlertService:
    """アラート判定・発火サービス"""

    def __init__(self):
        self._morning_alert_sent_today: Optional[str] = None

    async def check_inactivity(self) -> Optional[Alert]:
        """長時間不活動チェック"""
        threshold_minutes = settings.alert.inactivity_threshold_minutes
        now = datetime.now(JST)

        async with async_session() as session:
            result = await session.execute(
                select(ActivityEvent).order_by(desc(ActivityEvent.timestamp)).limit(1)
            )
            last_event = result.scalar_one_or_none()

            if last_event is None:
                return None

            last_time = last_event.timestamp
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=JST)

            elapsed_minutes = (now - last_time).total_seconds() / 60

            if elapsed_minutes >= threshold_minutes:
                existing = await session.execute(
                    select(Alert).where(
                        Alert.alert_type == AlertType.LONG_INACTIVITY,
                        Alert.status == AlertStatus.TRIGGERED,
                    )
                )
                if existing.scalar_one_or_none():
                    return None

                alert = Alert(
                    alert_type=AlertType.LONG_INACTIVITY,
                    status=AlertStatus.TRIGGERED,
                    message=f"{int(elapsed_minutes)}分間、活動が検知されていません。（最後の活動: {last_time.strftime('%H:%M')}）",
                    triggered_at=now,
                )
                session.add(alert)
                await session.commit()

                await line_service.send_alert(
                    alert_type="long_inactivity",
                    title="長時間動きがありません",
                    description=f"最後の活動から{int(elapsed_minutes)}分が経過しました。\n最後の検知: {last_time.strftime('%H:%M')} ({last_event.device_name})",
                    timestamp=now,
                )
                alert.notified = True
                await session.commit()

                logger.warning(f"不活動アラート発火: {int(elapsed_minutes)}分経過")
                return alert

        return None

    async def check_morning_activity(self) -> Optional[Alert]:
        """朝の安否確認"""
        now = datetime.now(JST)
        today_str = now.strftime("%Y-%m-%d")

        if self._morning_alert_sent_today == today_str:
            return None

        check_hour, check_minute = map(int, settings.alert.morning_check_time.split(":"))
        check_time = now.replace(hour=check_hour, minute=check_minute, second=0, microsecond=0)

        if now < check_time:
            return None

        if (now - check_time).total_seconds() > 1800:
            return None

        async with async_session() as session:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            result = await session.execute(
                select(func.count(ActivityEvent.id)).where(ActivityEvent.timestamp >= today_start)
            )
            event_count = result.scalar() or 0

            if event_count == 0:
                alert = Alert(
                    alert_type=AlertType.MORNING_NO_ACTIVITY,
                    status=AlertStatus.TRIGGERED,
                    message=f"本日 {today_str} の朝、まだ活動が検知されていません。",
                    triggered_at=now,
                )
                session.add(alert)
                await session.commit()

                await line_service.send_alert(
                    alert_type="morning_no_activity",
                    title="朝の活動が確認できません",
                    description=f"本日 {check_time.strftime('%H:%M')} 時点で、まだお母さんの活動が検知されていません。\n確認をお願いします。",
                    timestamp=now,
                )
                alert.notified = True
                await session.commit()

                self._morning_alert_sent_today = today_str
                logger.warning(f"朝の安否確認アラート発火: {today_str}")
                return alert

        return None

    async def resolve_alerts_on_activity(self):
        """活動が検知された場合、未解消のアラートを自動解消"""
        now = datetime.now(JST)

        async with async_session() as session:
            result = await session.execute(
                select(Alert).where(Alert.status == AlertStatus.TRIGGERED)
            )
            active_alerts = result.scalars().all()

            for alert in active_alerts:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = now

            if active_alerts:
                await session.commit()
                logger.info(f"{len(active_alerts)}件のアラートを自動解消しました")

    async def save_activity_event(self, event_data: dict) -> ActivityEvent:
        """活動イベントをDBに保存"""
        async with async_session() as session:
            event = ActivityEvent(
                event_type=event_data["event_type"],
                device_name=event_data["device_name"],
                device_id=event_data.get("device_id"),
                timestamp=event_data["timestamp"],
                details=event_data.get("details"),
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)

            await self.resolve_alerts_on_activity()
            return event

    async def update_daily_summary(self):
        """本日の日次サマリーを更新"""
        now = datetime.now(JST)
        today_str = now.strftime("%Y-%m-%d")
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async with async_session() as session:
            events_result = await session.execute(
                select(ActivityEvent)
                .where(ActivityEvent.timestamp >= today_start)
                .order_by(ActivityEvent.timestamp)
            )
            events = events_result.scalars().all()

            if not events:
                return

            motion_count = sum(1 for e in events if e.event_type == EventType.MOTION_DETECTED)
            plug_on_count = sum(1 for e in events if e.event_type == EventType.PLUG_ON)
            first_activity = events[0].timestamp
            last_activity = events[-1].timestamp

            max_inactivity = 0.0
            for i in range(1, len(events)):
                gap = (events[i].timestamp - events[i - 1].timestamp).total_seconds() / 60
                max_inactivity = max(max_inactivity, gap)

            alerts_result = await session.execute(
                select(func.count(Alert.id)).where(Alert.triggered_at >= today_start)
            )
            alerts_count = alerts_result.scalar() or 0

            existing = await session.execute(
                select(DailySummary).where(DailySummary.date == today_str)
            )
            summary = existing.scalar_one_or_none()

            if summary:
                summary.first_activity_time = first_activity
                summary.last_activity_time = last_activity
                summary.motion_count = motion_count
                summary.plug_on_count = plug_on_count
                summary.max_inactivity_minutes = max_inactivity
                summary.alerts_triggered = alerts_count
            else:
                summary = DailySummary(
                    date=today_str,
                    first_activity_time=first_activity,
                    last_activity_time=last_activity,
                    motion_count=motion_count,
                    plug_on_count=plug_on_count,
                    max_inactivity_minutes=max_inactivity,
                    alerts_triggered=alerts_count,
                )
                session.add(summary)

            await session.commit()


# シングルトンインスタンス
alert_service = AlertService()
