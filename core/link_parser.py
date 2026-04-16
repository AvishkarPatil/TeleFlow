from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from db.models import SourceType

_RANGE_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


@dataclass(frozen=True)
class ParsedLink:
    source_chat: str
    source_type: str
    msg_id_start: int
    msg_id_end: int
    invite_hash: Optional[str] = None
    raw_url: str = ""

    @property
    def is_range(self) -> bool:
        return self.msg_id_end > self.msg_id_start

    @property
    def message_count(self) -> int:
        return self.msg_id_end - self.msg_id_start + 1


def parse(url: str) -> Optional[ParsedLink]:
    url = url.strip()

    # Invite links
    if "https://t.me/+" in url or "https://t.me/joinchat/" in url:
        invite_hash = (
            url.split("https://t.me/+")[-1]
            if "https://t.me/+" in url
            else url.split("https://t.me/joinchat/")[-1]
        )
        return ParsedLink(
            source_chat="",
            source_type=SourceType.INVITE,
            msg_id_start=0,
            msg_id_end=0,
            invite_hash=invite_hash.split("?")[0].strip(),
            raw_url=url,
        )

    # Private channel: t.me/c/<chat_id>/<msg_id>
    # Topic variant:   t.me/c/<chat_id>/<topic_id>/<msg_id>
    if "https://t.me/c/" in url:
        parts = url.split("/")
        if len(parts) < 6:
            return None
        raw_chat_id = parts[4]
        # 7 parts means topic link — use parts[6] as msg_id
        if len(parts) >= 7 and parts[6].replace("?single", "").strip().isdigit():
            raw_msg = parts[6].replace("?single", "").strip()
        else:
            raw_msg = parts[5].replace("?single", "").strip()
        try:
            chat_id = int("-100" + raw_chat_id)
        except ValueError:
            return None
        start, end = _parse_id_range(raw_msg)
        if start is None:
            return None
        return ParsedLink(
            source_chat=str(chat_id),
            source_type=SourceType.PRIVATE,
            msg_id_start=start,
            msg_id_end=end,
            raw_url=url,
        )

    # Bot chat: t.me/b/<botusername>/<msg_id>
    if "https://t.me/b/" in url:
        parts = url.split("/")
        if len(parts) < 6:
            return None
        username = parts[4].strip()
        raw_msg = parts[5].replace("?single", "").strip()
        start, end = _parse_id_range(raw_msg)
        if start is None:
            return None
        return ParsedLink(
            source_chat=username,
            source_type=SourceType.BOT,
            msg_id_start=start,
            msg_id_end=end,
            raw_url=url,
        )

    # Public channel: t.me/<username>/<msg_id>
    # Topic variant:  t.me/<username>/<topic_id>/<msg_id>
    if "https://t.me/" in url:
        parts = url.split("/")
        if len(parts) < 5:
            return None
        username = parts[3].strip()
        # 6 parts means topic link — use parts[5] as msg_id
        if len(parts) >= 6 and parts[5].replace("?single", "").strip().isdigit():
            raw_msg = parts[5].replace("?single", "").strip()
        else:
            raw_msg = parts[4].replace("?single", "").strip()
        start, end = _parse_id_range(raw_msg)
        if start is None:
            return None
        return ParsedLink(
            source_chat=username,
            source_type=SourceType.PUBLIC,
            msg_id_start=start,
            msg_id_end=end,
            raw_url=url,
        )

    return None


def _parse_id_range(raw: str) -> tuple[Optional[int], int]:
    raw = raw.strip()
    match = _RANGE_RE.match(raw)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        if start > end:
            start, end = end, start
        return start, end
    if raw.isdigit():
        v = int(raw)
        return v, v
    return None, 0
