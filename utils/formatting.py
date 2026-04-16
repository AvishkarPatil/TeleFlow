from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(size: int) -> str:
    if size < 0:
        return "0 B"
    s = float(size)
    for unit in _UNITS[:-1]:
        if s < 1024.0:
            return f"{s:.1f} {unit}"
        s /= 1024.0
    return f"{s:.1f} {_UNITS[-1]}"


def format_speed(bytes_per_second: float) -> str:
    if bytes_per_second < 0:
        return "0 B/s"
    return f"{format_bytes(int(bytes_per_second))}/s"


def format_duration(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def format_eta(current: int, total: int, bps: float) -> str:
    if bps <= 0 or total <= 0:
        return "..."
    remaining = max(0, total - current)
    return format_duration(remaining / bps)


def format_percent(current: int, total: int) -> str:
    if total <= 0:
        return "0%"
    pct = min(100.0, current * 100 / total)
    return f"{pct:.0f}%"


def truncate(text: str, max_len: int = 50) -> str:
    if not text or len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"
