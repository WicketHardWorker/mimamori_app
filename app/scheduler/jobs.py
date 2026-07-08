"""定期実行ジョブ

APSchedulerを使用してTapoデバイスのポーリングとアラートチェックを定期実行する。
"""

import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.tapo_monitor import tapo_monitor
from app.services.alert_service import alert_service
from app.services.line_notify import line_service

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")



async def poll_devices_job():
    """デバイスポーリングジョブ"""
    try:
        events = await tapo_monitor.poll_all_devices()
        for event_data in events:
            await alert_service.save_activity_event(event_data)
        if events:
            await alert_service.update_daily_summary()
    except Exception as e:
        logger.error(f"デバイスポーリングジョブでエラー: {e}")


async def check_inactivity_job():
    """不活動チェックジョブ"""
    try:
        await alert_service.check_inactivity()
    except Exception as e:
        logger.error(f"不活動チェックジョブでエラー: {e}")


async def morning_check_job():
    """朝の安否確認ジョブ"""
    try:
        await alert_service.check_morning_activity()
    except Exception as e:
        logger.error(f"朝の安否確認ジョブでエラー: {e}")



async def daily_report_job():
    """日次レポート送信ジョブ"""
    try:
        from sqlalchemy import select
        from app.database import async_session
        from app.models import DailySummary

        now = datetime.now(JST)
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        async with async_session() as session:
            result = await session.execute(
                select(DailySummary).where(DailySummary.date == yesterday)
            )
            summary = result.scalar_one_or_none()

        if summary:
            first_time = summary.first_activity_time.strftime("%H:%M") if summary.first_activity_time else None
            last_time = summary.last_activity_time.strftime("%H:%M") if summary.last_activity_time else None
            await line_service.send_daily_report(
                date_str=yesterday,
                first_activity=first_time,
                last_activity=last_time,
                motion_count=summary.motion_count,
                plug_on_count=summary.plug_on_count,
                max_inactivity_min=summary.max_inactivity_minutes,
            )
        else:
            await line_service.send_daily_report(
                date_str=yesterday, first_activity=None, last_activity=None,
                motion_count=0, plug_on_count=0, max_inactivity_min=0,
            )
    except Exception as e:
        logger.error(f"日次レポートジョブでエラー: {e}")



def setup_scheduler():
    """スケジューラのセットアップ"""
    polling_interval = settings.alert.polling_interval_seconds

    scheduler.add_job(
        poll_devices_job,
        trigger=IntervalTrigger(seconds=polling_interval),
        id="poll_devices", name="デバイスポーリング", replace_existing=True,
    )
    scheduler.add_job(
        check_inactivity_job,
        trigger=IntervalTrigger(minutes=5),
        id="check_inactivity", name="不活動チェック", replace_existing=True,
    )

    check_hour, check_minute = map(int, settings.alert.morning_check_time.split(":"))
    scheduler.add_job(
        morning_check_job,
        trigger=CronTrigger(hour=check_hour, minute=check_minute),
        id="morning_check", name="朝の安否確認", replace_existing=True,
    )
    scheduler.add_job(
        daily_report_job,
        trigger=CronTrigger(hour=21, minute=0),
        id="daily_report", name="日次レポート送信", replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"スケジューラを起動しました "
        f"(ポーリング: {polling_interval}秒, "
        f"朝チェック: {settings.alert.morning_check_time}, "
        f"不活動閾値: {settings.alert.inactivity_threshold_minutes}分)"
    )


def shutdown_scheduler():
    """スケジューラの停止"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("スケジューラを停止しました")
