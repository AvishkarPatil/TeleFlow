from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


class TaskStatus:
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"


class SourceType:
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    BOT = "BOT"
    INVITE = "INVITE"


class ThumbMode:
    DEFAULT = "default"   # use original thumb from source as-is
    NONE    = "none"      # extract middle frame from video
    CUSTOM  = "custom"    # use user-uploaded thumbnail


@dataclass
class UserPrefs:
    dest_channel_id:    Optional[int]   = None
    dest_channel_title: Optional[str]   = None
    thumbnail_file_id:  Optional[str]   = None
    thumbnail_mode:     str             = ThumbMode.DEFAULT
    filename_template:  Optional[str]   = None
    caption_template:   Optional[str]   = None
    caption_filters:    List[str]       = field(default_factory=list)
    bot_mode:           bool            = False  # if True, bot tries copy first

    def to_dict(self) -> dict:
        return {
            "dest_channel_id":    self.dest_channel_id,
            "dest_channel_title": self.dest_channel_title,
            "thumbnail_file_id":  self.thumbnail_file_id,
            "thumbnail_mode":     self.thumbnail_mode,
            "filename_template":  self.filename_template,
            "caption_template":   self.caption_template,
            "caption_filters":    self.caption_filters,
            "bot_mode":           self.bot_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> UserPrefs:
        return cls(
            dest_channel_id=d.get("dest_channel_id"),
            dest_channel_title=d.get("dest_channel_title"),
            thumbnail_file_id=d.get("thumbnail_file_id"),
            thumbnail_mode=d.get("thumbnail_mode", ThumbMode.DEFAULT).replace("original", ThumbMode.DEFAULT),
            filename_template=d.get("filename_template"),
            caption_template=d.get("caption_template"),
            caption_filters=d.get("caption_filters", []),
            bot_mode=d.get("bot_mode", False),
        )


@dataclass
class TaskDocument:
    task_id: str
    user_id: int
    status: str = TaskStatus.PENDING
    source_chat: str = ""
    source_type: str = SourceType.PUBLIC
    msg_id_start: int = 0
    msg_id_end: int = 0
    msg_id_current: Optional[int] = None
    media_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    retry_count: int = 0
    status_chat_id: Optional[int] = None
    status_msg_id: Optional[int] = None
    user_chat_id: Optional[int] = None  # always the user's DM — for status messages

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "status": self.status,
            "source_chat": self.source_chat,
            "source_type": self.source_type,
            "msg_id_start": self.msg_id_start,
            "msg_id_end": self.msg_id_end,
            "msg_id_current": self.msg_id_current,
            "media_type": self.media_type,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "retry_count": self.retry_count,
            "status_chat_id": self.status_chat_id,
            "status_msg_id": self.status_msg_id,
            "user_chat_id": self.user_chat_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TaskDocument:
        return cls(
            task_id=d["task_id"],
            user_id=d["user_id"],
            status=d.get("status", TaskStatus.PENDING),
            source_chat=d.get("source_chat", ""),
            source_type=d.get("source_type", SourceType.PUBLIC),
            msg_id_start=d.get("msg_id_start", 0),
            msg_id_end=d.get("msg_id_end", 0),
            msg_id_current=d.get("msg_id_current"),
            media_type=d.get("media_type"),
            file_name=d.get("file_name"),
            file_size=d.get("file_size"),
            created_at=d.get("created_at", datetime.utcnow()),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            error=d.get("error"),
            retry_count=d.get("retry_count", 0),
            status_chat_id=d.get("status_chat_id"),
            status_msg_id=d.get("status_msg_id"),
            user_chat_id=d.get("user_chat_id"),
        )


@dataclass
class UserDocument:
    user_id: int
    username: Optional[str] = None
    first_name: str = ""
    is_sudo: bool = False
    is_blocked: bool = False
    added_by: Optional[int] = None
    added_at: datetime = field(default_factory=datetime.utcnow)
    total_tasks: int = 0
    total_bytes_transferred: int = 0
    prefs: UserPrefs = field(default_factory=UserPrefs)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "is_sudo": self.is_sudo,
            "is_blocked": self.is_blocked,
            "added_by": self.added_by,
            "added_at": self.added_at,
            "total_tasks": self.total_tasks,
            "total_bytes_transferred": self.total_bytes_transferred,
            "prefs": self.prefs.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> UserDocument:
        return cls(
            user_id=d["user_id"],
            username=d.get("username"),
            first_name=d.get("first_name", ""),
            is_sudo=d.get("is_sudo", False),
            is_blocked=d.get("is_blocked", False),
            added_by=d.get("added_by"),
            added_at=d.get("added_at", datetime.utcnow()),
            total_tasks=d.get("total_tasks", 0),
            total_bytes_transferred=d.get("total_bytes_transferred", 0),
            prefs=UserPrefs.from_dict(d.get("prefs") or {}),
        )


@dataclass
class TransferLogDocument:
    task_id: str
    user_id: int
    source_chat: str
    msg_id: int
    media_type: str
    file_name: Optional[str]
    file_size: int
    duration_seconds: float
    avg_speed_bps: float
    success: bool
    error: Optional[str]
    logged_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "source_chat": self.source_chat,
            "msg_id": self.msg_id,
            "media_type": self.media_type,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "duration_seconds": self.duration_seconds,
            "avg_speed_bps": self.avg_speed_bps,
            "success": self.success,
            "error": self.error,
            "logged_at": self.logged_at,
        }
