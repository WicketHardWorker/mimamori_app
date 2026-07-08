"""LINE通知サービス

LINE Messaging APIを使用して見守りアラートを送信する。
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from linebot.v3.messaging import (
    Configuration,
    AsyncApiClient,
    AsyncMessagingApi,
    PushMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from app.config import settings

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


class LineNotifyService:
    """LINE Messaging APIを使った通知サービス"""

    def __init__(self):
        self._api: Optional[AsyncMessagingApi] = None
        self._initialized = False

    async def initialize(self):
        """LINE APIクライアントの初期化"""
        try:
            if not settings.line.channel_access_token:
                logger.warning(
                    "LINE Channel Access Token が設定されていません。通知機能は無効です。"
                )
                return

            configuration = Configuration(access_token=settings.line.channel_access_token)
            async_api_client = AsyncApiClient(configuration)
            self._api = AsyncMessagingApi(async_api_client)
            self._initialized = True
            logger.info("LINE通知サービスの初期化が完了しました")

        except Exception as e:
            logger.error(f"LINE通知サービスの初期化に失敗: {e}")
            self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def send_text_message(self, message: str) -> bool:
        """テキストメッセージを送信"""
        if not self._initialized or not self._api:
            logger.warning("LINE通知サービスが未初期化のため送信をスキップ")
            return False

        try:
            request = PushMessageRequest(
                to=settings.line.target_user_id,
                messages=[TextMessage(text=message)],
            )
            await self._api.push_message(request)
            logger.info(f"LINE通知を送信しました: {message[:50]}...")
            return True

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
        if not self._initialized or not self._api:
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
            flex_container = FlexContainer.from_dict(flex_content)
            request = PushMessageRequest(
                to=settings.line.target_user_id,
                messages=[FlexMessage(alt_text=f"{emoji} {title}", contents=flex_container)],
            )
            await self._api.push_message(request)
            logger.info(f"LINEアラートを送信しました: {title}")
            return True

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
        self._initialized = False
        self._api = None
        logger.info("LINE通知サービスを終了しました")


# シングルトンインスタンス
line_service = LineNotifyService()
