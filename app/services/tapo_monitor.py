"""Tapoデバイス監視サービス

H100ハブ経由でT100モーションセンサーの状態を取得し、
P110Mスマートプラグの消費電力を監視する。
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

# 電力閾値（ミリワット）: これを超えたら「使用中」と判定
# 電気ケトルは通常800W〜1200W = 800000〜1200000 mW
# 待機電力は通常 0〜5W 程度
POWER_ON_THRESHOLD_MW = 10000    # 10W以上で「使用開始」
POWER_OFF_THRESHOLD_MW = 5000   # 5W以下で「使用終了」


class TapoMonitorService:
    """Tapoデバイスの監視を行うサービスクラス"""

    def __init__(self):
        self._client: Optional[ApiClient] = None
        self._hub = None
        self._plug = None
        self._last_motion_time: Optional[datetime] = None
        self._last_plug_state: Optional[bool] = None  # ON/OFF状態
        self._is_appliance_active: bool = False  # 家電が実際に稼働中か（電力ベース）
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

            # P110Mプラグに接続（電力モニタリング対応）
            if settings.tapo.p100m_ip:
                self._plug = await self._client.p110(settings.tapo.p100m_ip)
                logger.info(f"P110Mプラグに接続しました: {settings.tapo.p100m_ip}")

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
        """H100ハブ経由でT100モーションセンサーの状態を確認

        2つの方法で検知を試みる:
        1. get_trigger_logs() でイベント履歴を取得（正確な時刻が取れる）
        2. フォールバック: get_child_device_list() で detected フラグを確認
        """
        events = []

        if not self._hub:
            logger.warning("H100ハブが未接続です")
            return events

        # === 方法1: トリガーログから取得（正確な検知時刻が取れる） ===
        try:
            trigger_logs = await self._hub.get_trigger_logs(page_size=20)
            logs = getattr(trigger_logs, "logs", None) or getattr(trigger_logs, "entries", None) or trigger_logs

            if logs and hasattr(logs, '__iter__'):
                for log_entry in logs:
                    ts = getattr(log_entry, "timestamp", None) or getattr(log_entry, "time", None)
                    if ts is None:
                        continue

                    if isinstance(ts, (int, float)):
                        event_time = datetime.fromtimestamp(ts, tz=JST)
                    elif isinstance(ts, datetime):
                        event_time = ts if ts.tzinfo else ts.replace(tzinfo=JST)
                    else:
                        continue

                    if (
                        self._last_motion_time is not None
                        and event_time <= self._last_motion_time
                    ):
                        continue

                    device_id = getattr(log_entry, "device_id", "unknown")
                    nickname = getattr(log_entry, "nickname", None) or "T100 センサー"

                    event = {
                        "event_type": EventType.MOTION_DETECTED,
                        "device_name": nickname,
                        "device_id": device_id,
                        "timestamp": event_time,
                        "details": json.dumps(
                            {"source": "T100", "method": "trigger_logs"},
                            ensure_ascii=False,
                        ),
                    }
                    events.append(event)

                if events:
                    self._last_motion_time = max(e["timestamp"] for e in events)
                    logger.info(
                        f"トリガーログから {len(events)} 件のモーション検知を取得"
                    )
                    return events

        except (AttributeError, TypeError) as e:
            logger.debug(f"トリガーログ取得をスキップ（未対応）: {e}")
        except Exception as e:
            if "SESSION_TIMEOUT" in str(e) or "Unauthorized" in str(e):
                logger.warning(f"セッション切れを検知、再接続します: {e}")
                await self.reconnect()
                return events
            logger.debug(f"トリガーログ取得でエラー（フォールバックへ）: {e}")

        # === 方法2: フォールバック - detected フラグによるポーリング ===
        try:
            child_device_list = await self._hub.get_child_device_list()

            for device in child_device_list:
                if hasattr(device, "detected") or "T100" in str(
                    getattr(device, "model", "")
                ):
                    detected = getattr(device, "detected", False)
                    device_id = getattr(device, "device_id", "unknown")
                    nickname = getattr(device, "nickname", "T100 センサー")

                    if not detected:
                        continue

                    event_time = None
                    for attr in ("last_onboarding_timestamp", "triggered_at", "timestamp"):
                        ts = getattr(device, attr, None)
                        if ts is not None:
                            if isinstance(ts, (int, float)) and ts > 0:
                                event_time = datetime.fromtimestamp(ts, tz=JST)
                            elif isinstance(ts, datetime):
                                event_time = ts if ts.tzinfo else ts.replace(tzinfo=JST)
                            break

                    if event_time is None:
                        event_time = datetime.now(JST)

                    if (
                        self._last_motion_time is not None
                        and event_time <= self._last_motion_time
                    ):
                        continue

                    self._last_motion_time = event_time
                    event = {
                        "event_type": EventType.MOTION_DETECTED,
                        "device_name": nickname,
                        "device_id": device_id,
                        "timestamp": event_time,
                        "details": json.dumps(
                            {"detected": True, "source": "T100", "method": "polling"},
                            ensure_ascii=False,
                        ),
                    }
                    events.append(event)
                    logger.info(
                        f"モーション検知: {nickname} ({event_time.strftime('%H:%M:%S')})"
                    )

        except Exception as e:
            if "SESSION_TIMEOUT" in str(e) or "Unauthorized" in str(e):
                logger.warning(f"セッション切れを検知、再接続します: {e}")
                await self.reconnect()
            else:
                logger.error(f"モーションセンサーの確認中にエラー: {e}")

        return events

    async def check_plug_status(self) -> list[dict]:
        """P110Mスマートプラグの消費電力を監視して家電使用を検知"""
        events = []

        if not self._plug:
            logger.warning("P110Mプラグが未接続です")
            return events

        try:
            # 現在の消費電力を取得
            energy_usage = await self._plug.get_current_power()
            current_power_mw = getattr(energy_usage, "current_power", 0)  # ミリワット

            device_info = await self._plug.get_device_info()
            nickname = getattr(device_info, "nickname", "電気ケトル")
            device_id = getattr(device_info, "device_id", "unknown")
            now = datetime.now(JST)

            current_power_w = current_power_mw / 1000  # ワットに変換

            # 電力ベースで家電の使用開始/終了を判定
            if not self._is_appliance_active and current_power_mw > POWER_ON_THRESHOLD_MW:
                # 使用開始を検知！
                self._is_appliance_active = True
                event = {
                    "event_type": EventType.PLUG_ON,
                    "device_name": nickname,
                    "device_id": device_id,
                    "timestamp": now,
                    "details": json.dumps(
                        {
                            "current_power_w": current_power_w,
                            "source": "P110M",
                            "detection": "power_threshold",
                        },
                        ensure_ascii=False,
                    ),
                }
                events.append(event)
                logger.info(
                    f"⚡ 家電使用開始: {nickname} ({current_power_w:.1f}W) "
                    f"({now.strftime('%H:%M:%S')})"
                )

            elif self._is_appliance_active and current_power_mw < POWER_OFF_THRESHOLD_MW:
                # 使用終了を検知
                self._is_appliance_active = False
                event = {
                    "event_type": EventType.PLUG_OFF,
                    "device_name": nickname,
                    "device_id": device_id,
                    "timestamp": now,
                    "details": json.dumps(
                        {
                            "current_power_w": current_power_w,
                            "source": "P110M",
                            "detection": "power_threshold",
                        },
                        ensure_ascii=False,
                    ),
                }
                events.append(event)
                logger.info(
                    f"⚡ 家電使用終了: {nickname} ({current_power_w:.1f}W) "
                    f"({now.strftime('%H:%M:%S')})"
                )

        except Exception as e:
            if "SESSION_TIMEOUT" in str(e) or "Unauthorized" in str(e):
                logger.warning(f"セッション切れを検知（プラグ）、再接続します: {e}")
                await self.reconnect()
            else:
                logger.error(f"プラグ電力監視中にエラー: {e}")

        return events

    async def reconnect(self):
        """セッション切れ時に再接続"""
        logger.info("Tapoデバイスに再接続を試みます...")
        try:
            self._client = ApiClient(
                settings.tapo.username,
                settings.tapo.password,
            )
            if settings.tapo.h100_ip:
                self._hub = await self._client.h100(settings.tapo.h100_ip)
            if settings.tapo.p100m_ip:
                self._plug = await self._client.p110(settings.tapo.p100m_ip)
            self._initialized = True
            logger.info("✅ Tapoデバイスへの再接続に成功しました")
        except Exception as e:
            logger.error(f"再接続に失敗しました: {e}")
            self._initialized = False

    async def poll_all_devices(self) -> list[dict]:
        """全デバイスをポーリングしてイベントを収集"""
        if not self._initialized:
            logger.warning("Tapo監視サービスが初期化されていません")
            return []

        all_events = []

        # モーションセンサー（エラーでも続行）
        try:
            motion_events = await self.check_motion_sensor()
            all_events.extend(motion_events)
        except Exception as e:
            logger.error(f"モーションセンサーチェック失敗: {e}")

        # プラグ（エラーでも続行）
        try:
            plug_events = await self.check_plug_status()
            all_events.extend(plug_events)
        except Exception as e:
            logger.error(f"プラグチェック失敗: {e}")

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
                energy = await self._plug.get_current_power()
                current_power_mw = getattr(energy, "current_power", 0)
                current_power_w = current_power_mw / 1000
                statuses.append({
                    "device_name": getattr(plug_info, "nickname", "電気ケトル"),
                    "device_type": "plug",
                    "ip_address": settings.tapo.p100m_ip,
                    "is_online": True,
                    "last_seen": now,
                    "last_event": f"{current_power_w:.1f}W {'⚡使用中' if self._is_appliance_active else '待機'}",
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
