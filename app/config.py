"""アプリケーション設定モジュール"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()


@dataclass
class TapoConfig:
    """Tapoデバイス接続設定"""
    username: str = field(default_factory=lambda: os.getenv("TAPO_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("TAPO_PASSWORD", ""))
    h100_ip: str = field(default_factory=lambda: os.getenv("TAPO_H100_IP", ""))
    p100m_ip: str = field(default_factory=lambda: os.getenv("TAPO_P100M_IP", ""))


@dataclass
class LineConfig:
    """LINE Messaging API設定"""
    channel_access_token: str = field(
        default_factory=lambda: os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    )
    channel_secret: str = field(
        default_factory=lambda: os.getenv("LINE_CHANNEL_SECRET", "")
    )
    target_user_id: str = field(
        default_factory=lambda: os.getenv("LINE_TARGET_USER_ID", "")
    )


@dataclass
class AlertConfig:
    """アラート設定"""
    morning_check_time: str = field(
        default_factory=lambda: os.getenv("MORNING_CHECK_TIME", "08:00")
    )
    inactivity_threshold_minutes: int = field(
        default_factory=lambda: int(os.getenv("INACTIVITY_THRESHOLD_MINUTES", "180"))
    )
    polling_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("POLLING_INTERVAL_SECONDS", "60"))
    )


@dataclass
class AppConfig:
    """アプリケーション全体設定"""
    port: int = field(default_factory=lambda: int(os.getenv("APP_PORT", "8000")))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./mimamori.db")
    )
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Tokyo"))
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    # サブ設定
    tapo: TapoConfig = field(default_factory=TapoConfig)
    line: LineConfig = field(default_factory=LineConfig)
    alert: AlertConfig = field(default_factory=AlertConfig)


# シングルトンの設定インスタンス
settings = AppConfig()
