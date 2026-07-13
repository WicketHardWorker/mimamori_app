"""LINE通知サービス

httpxを使用してLINE Messaging APIに直接リクエストを送信する。
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

LINE_API_BROADCAST = "https://api.line.me/v2/bot/message/broadcast"


class LineNotifyService:
    """LINE Messaging APIを使った通知サービス（httpx版）"""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

    async def initialize(self):
        """HTTPクライアントの初期化"""
        try:
            if not settings.line.channel_access_token:
                logger.warning(
                    "LINE Channel Access Token が設定されていません。通知機能は無効です。"
                )
                return

            import certifi
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {settings.line.channel_access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
                verify=False,
            )
            self._initialized = True
            logger.info("LINE通知サービスの初期化が完了しました")

        except Exception as e:
            logger.error(f"LINE通知サービスの初期化に失敗: {e}")
            self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def send_text_message(self, message: str) -> bool:
        """テキストメッセージを友だち全員に送信"""
        if not self._initialized or not self._client:
            logger.warning("LINE通知サービスが未初期化のため送信をスキップ")
            return False

        try:
            payload = {
                "messages": [{"type": "text", "text": message}]
            }
            response = await self._client.post(LINE_API_BROADCAST, json=payload)

            if response.status_code == 200:
                logger.info(f"LINE通知を送信しました: {message[:50]}...")
                return True
            else:
                logger.error(f"LINE通知の送信に失敗 (HTTP {response.status_code}): {response.text}")
                return False

        except Exception as e:
            logger.error(f"LINE通知の送信に失敗: {e}")
            return False

    async def send_alert(
        self,
        alert_type: str,
        title: str,
        description: str,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """アラート通知を送信（Flex Message装飾付き）"""
        if not self._initialized or not self._client:
            logger.warning("LINE通知サービスが未初期化のため送信をスキップ")
            return False

        if timestamp is None:
            timestamp = datetime.now(JST)

        time_str = timestamp.strftime("%Y/%m/%d %H:%M")

        emoji_map = {
            "morning_no_activity": "🌅",
            "long_inactivity": "⚠️",
            "device_offline": "📡",
        }
        emoji = emoji_map.get(alert_type, "🔔")

        flex_content = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{emoji} 見守りアラート",
                        "weight": "bold",
                        "size": "md",
                        "color": "#E74C3C",
                    }
                ],
                "backgroundColor": "#FFF3F3",
                "paddingAll": "lg",
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "lg", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": description, "size": "sm", "color": "#555555", "wrap": True, "margin": "md"},
                    {"type": "text", "text": f"🕐 {time_str}", "size": "xs", "color": "#888888", "margin": "lg"},
                ],
                "paddingAll": "lg",
            },
        }

        try:
            payload = {
                "messages": [
                    {
                        "type": "flex",
                        "altText": f"{emoji} {title}",
                        "contents": flex_content,
                    }
                ]
            }
            response = await self._client.post(LINE_API_BROADCAST, json=payload)

            if response.status_code == 200:
                logger.info(f"LINEアラートを送信しました: {title}")
                return True
            else:
                logger.error(f"LINEアラートの送信に失敗 (HTTP {response.status_code}): {response.text}")
                # フォールバック: テキストメッセージで送信
                fallback_msg = f"{emoji} 【見守りアラート】\n\n■ {title}\n{description}\n\n🕐 {time_str}"
                return await self.send_text_message(fallback_msg)

        except Exception as e:
            logger.error(f"LINEアラートの送信に失敗: {e}")
            fallback_msg = f"{emoji} 【見守りアラート】\n\n■ {title}\n{description}\n\n🕐 {time_str}"
            return await self.send_text_message(fallback_msg)

    async def send_daily_report(
        self,
        date_str: str,
        first_activity: Optional[str],
        last_activity: Optional[str],
        motion_count: int,
        plug_on_count: int,
        max_inactivity_min: float,
    ) -> bool:
        """日次レポートを送信"""
        report = (
            f"📊 【日次レポート】{date_str}\n\n"
            f"🌅 最初の活動: {first_activity or '検知なし'}\n"
            f"🌙 最後の活動: {last_activity or '検知なし'}\n"
            f"🚶 動き検知回数: {motion_count}回\n"
            f"🔌 家電使用回数: {plug_on_count}回\n"
            f"⏱️ 最大不活動時間: {max_inactivity_min:.0f}分\n"
        )

        if max_inactivity_min > settings.alert.inactivity_threshold_minutes:
            report += f"\n⚠️ 長時間の不活動がありました"

        return await self.send_text_message(report)

    async def close(self):
        """リソースのクリーンアップ"""
        if self._client:
            await self._client.aclose()
        self._initialized = False
        self._client = None
        logger.info("LINE通知サービスを終了しました")


# シングルトンインスタンス
line_service = LineNotifyService()
