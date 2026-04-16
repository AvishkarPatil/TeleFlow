from __future__ import annotations

from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pyrogram.types import Message


class MediaKind(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    VOICE = "voice"
    ANIMATION = "animation"
    STICKER = "sticker"
    TEXT = "text"
    UNKNOWN = "unknown"


def detect(message: "Message") -> MediaKind:
    if message.media is None:
        return MediaKind.TEXT if message.text else MediaKind.UNKNOWN

    from pyrogram.enums import MessageMediaType
    _MAP = {
        MessageMediaType.PHOTO: MediaKind.PHOTO,
        MessageMediaType.VIDEO: MediaKind.VIDEO,
        MessageMediaType.DOCUMENT: MediaKind.DOCUMENT,
        MessageMediaType.AUDIO: MediaKind.AUDIO,
        MessageMediaType.VOICE: MediaKind.VOICE,
        MessageMediaType.ANIMATION: MediaKind.ANIMATION,
        MessageMediaType.STICKER: MediaKind.STICKER,
    }
    return _MAP.get(message.media, MediaKind.UNKNOWN)


def has_media(message: "Message") -> bool:
    return detect(message) not in (MediaKind.TEXT, MediaKind.UNKNOWN)


def get_file_ref(message: "Message") -> Optional[object]:
    kind = detect(message)
    return getattr(message, kind.value, None)
