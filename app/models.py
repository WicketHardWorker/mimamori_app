"""データベースモデル定義"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Enum, Text
from sqlalchemy.sql import func

from app.database import Base


class EventType(str, PyEnum):
    """イベント種別"""
    MOTION_DETECTED = "motion_detected"
    PLUG_ON = "plug_on"
    PLUG_OFF = "plug_off"


class AlertType(str, PyEnum):
    """アラート種別"""
    MORNING_NO_ACTIVITY = "morning_no_activity"
    LONG_INACTIVITY = "long_inactivity"
    DEVICE_OFFLINE = "device_offline"


class AlertStatus(str, PyEnum):
    """アラートステータス"""
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ActivityEvent(Base):
    """活動イベント"""
    __tablename__ = "activity_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(Enum(EventType), nullable=False, index=True)
    device_name = Column(String(100), nullable=False)
    device_id = Column(String(100), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=func.now(), index=True)
    details = Column(Text, nullable=True)


class Alert(Base):
    """アラート履歴"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(Enum(AlertType), nullable=False, index=True)
    status = Column(Enum(AlertStatus), nullable=False, default=AlertStatus.TRIGGERED)
    message = Column(Text, nullable=False)
    triggered_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    notified = Column(Boolean, default=False)


class DeviceStatus(Base):
    """デバイスの最新状態"""
    __tablename__ = "device_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_name = Column(String(100), nullable=False, unique=True)
    device_type = Column(String(50), nullable=False)
    ip_address = Column(String(50), nullable=True)
    is_online = Column(Boolean, default=True)
    last_seen = Column(DateTime, nullable=True)
    last_event = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class DailySummary(Base):
    """日次サマリー"""
    __tablename__ = "daily_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, unique=True, index=True)
    first_activity_time = Column(DateTime, nullable=True)
    last_activity_time = Column(DateTime, nullable=True)
    motion_count = Column(Integer, default=0)
    plug_on_count = Column(Integer, default=0)
    max_inactivity_minutes = Column(Float, default=0.0)
    alerts_triggered = Column(Integer, default=0)
