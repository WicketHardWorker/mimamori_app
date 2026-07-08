"""Tapoデバイス監視サービス

H100ハブ経由でT100モーションセンサーの状態を取得し、
P100Mスマートプラグの電源状態を監視する。
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from tapo import ApiClient

from app.config import settings
from app.models import EventType

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


class TapoMonitorService:
    """Tapoデバイスの監視を行うサービスクラス"""

    def __init__(self):
        self._client: Optional[ApiClient] = None
        self._hub = None
        self._plug = None
        self._last_motion_time: Optional[datetime] = None
        self._last_plug_state: Optional[bool] = None
        self._initialized = False

    async def initialize(self):
        """Tapo APIクライアントの初期化・接続"""
        try:
            self._client = ApiClient(
                settings.tapo.username,
                settings.tapo.password,
            )

            # H100ハブに接続
            if settings.tapo.h100_ip:
                self._hub = await self._client.h100(settings.tapo.h100_ip)
                logger.info(f"H100ハブに接続しました: {settings.tapo.h100_ip}")

            # P100Mプラグに接続
            if settings.tapo.p100m_ip:
                self._plug = await self._client.p100(settings.tapo.p100m_ip)
                logger.info(f"P100Mプラグに接続しました: {settings.tapo.p100m_ip}")

            self._initialized = True
            logger.info("Tapo監視サービスの初期化が完了しました")

        except Exception as e:
            logger.error(f"Tapo監視サービスの初期化に失敗しました: {e}")
            self._initialized = False
            raise

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def check_motion_sensor(self) -> list[dict]:
        """H100ハブ経由でT100モーションセンサーの状態を確認"""
        events = []

        if not self._hub:
            logger.warning("H100ハブが未接続です")
            return events

        try:
            child_device_list = await self._hub.get_child_device_list()

            for device in child_device_list:
                if hasattr(device, "detected") or "T100" in str(
                    getattr(device, "model", "")
                ):
                    now = datetime.now(JST)
                    detected = getattr(device, "detected", False)
                    device_id = getattr(device, "device_id", "unknown")
                    nickname = getattr(device, "nickname", "T100 センサー")

                    if detected:
                        if (
                            self._last_motion_time is None
                            or (now - self._last_motion_time).total_seconds() > 30
                        ):
                            self._last_motion_time = now
                            event = {
                                "event_type": EventType.MOTION_DETECTED,
                                "device_name": nickname,
                                "device_id": device_id,
                                "timestamp": now,
                                "details": json.dumps(
                                    {"detected": True, "source": "T100"},
                                    ensure_ascii=False,
                                ),
                            }
                            events.append(event)
                            logger.info(
                                f"モーション検知: {nickname} ({now.strftime('%H:%M:%S')})"
                            )

        except Exception as e:
            logger.error(f"モーションセンサーの確認中にエラー: {e}")

        return events

    async def check_plug_status(self) -> list[dict]:
        """P100Mスマートプラグの電源状態を確認"""
        events = []

        if not self._plug:
            logger.warning("P100Mプラグが未接続です")
            return events

        try:
            device_info = await self._plug.get_device_info()
            is_on = device_info.device_on
            nickname = getattr(device_info, "nickname", "電気ケトル")
            device_id = getattr(device_info, "device_id", "unknown")
            now = datetime.now(JST)

            if self._last_plug_state is not None and self._last_plug_state != is_on:
                event_type = EventType.PLUG_ON if is_on else EventType.PLUG_OFF
                event = {
                    "event_type": event_type,
                    "device_name": nickname,
                    "device_id": device_id,
                    "timestamp": now,
                    "details": json.dumps(
                        {
                            "device_on": is_on,
                            "source": "P100M",
                            "on_time": getattr(device_info, "on_time", 0),
                        },
                        ensure_ascii=False,
                    ),
                }
                events.append(event)
                logger.info(
                    f"プラグ状態変化: {nickname} → {'ON' if is_on else 'OFF'} "
                    f"({now.strftime('%H:%M:%S')})"
                )

            self._last_plug_state = is_on

        except Exception as e:
            logger.error(f"プラグ状態の確認中にエラー: {e}")

        return events

    async def poll_all_devices(self) -> list[dict]:
        """全デバイスをポーリングしてイベントを収集"""
        if not self._initialized:
            logger.warning("Tapo監視サービスが初期化されていません")
            return []

        all_events = []
        motion_events = await self.check_motion_sensor()
        all_events.extend(motion_events)
        plug_events = await self.check_plug_status()
        all_events.extend(plug_events)

        return all_events

    async def get_device_statuses(self) -> list[dict]:
        """全デバイスの現在のステータスを取得"""
        statuses = []
        now = datetime.now(JST)

        if self._hub:
            try:
                hub_info = await self._hub.get_device_info()
                statuses.append({
                    "device_name": getattr(hub_info, "nickname", "H100 ハブ"),
                    "device_type": "hub",
                    "ip_address": settings.tapo.h100_ip,
                    "is_online": True,
                    "last_seen": now,
                })
            except Exception:
                statuses.append({
                    "device_name": "H100 ハブ",
                    "device_type": "hub",
                    "ip_address": settings.tapo.h100_ip,
                    "is_online": False,
                    "last_seen": None,
                })

        if self._plug:
            try:
                plug_info = await self._plug.get_device_info()
                statuses.append({
                    "device_name": getattr(plug_info, "nickname", "電気ケトル"),
                    "device_type": "plug",
                    "ip_address": settings.tapo.p100m_ip,
                    "is_online": True,
                    "last_seen": now,
                    "last_event": f"{'ON' if plug_info.device_on else 'OFF'}",
                })
            except Exception:
                statuses.append({
                    "device_name": "電気ケトル",
                    "device_type": "plug",
                    "ip_address": settings.tapo.p100m_ip,
                    "is_online": False,
                    "last_seen": None,
                })

        if self._hub:
            try:
                child_device_list = await self._hub.get_child_device_list()
                for device in child_device_list:
                    model = getattr(device, "model", "")
                    if "T100" in str(model):
                        statuses.append({
                            "device_name": getattr(device, "nickname", "T100 センサー"),
                            "device_type": "sensor",
                            "ip_address": None,
                            "is_online": getattr(device, "status", 0) == 0,
                            "last_seen": now,
                        })
            except Exception:
                pass

        return statuses

    async def close(self):
        """リソースのクリーンアップ"""
        self._initialized = False
        self._hub = None
        self._plug = None
        self._client = None
        logger.info("Tapo監視サービスを終了しました")


# シングルトンインスタンス
tapo_monitor = TapoMonitorService()
