import html as html_module
from datetime import datetime, timezone

from markupsafe import Markup


def ensure_tz(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def strftime_filter(value, fmt="%-d %b %Y, %H:%M"):
    value = ensure_tz(value)
    if value is None:
        return ""
    return value.astimezone().strftime(fmt)


UNITS = (
    (60, 1, "second"),
    (3600, 60, "minute"),
    (86400, 3600, "hour"),
    (604800, 86400, "day"),
    (2629800, 604800, "week"),
    (31557600, 2629800, "month"),
    (None, 31557600, "year"),
)


def span(secs):
    for limit, size, unit in UNITS:
        if limit is None or secs < limit:
            n = secs // size
            return f"{n} {unit}" if n == 1 else f"{n} {unit}s"


def duration_filter(seconds):
    parts = []
    for size, unit in ((3600, "hour"), (60, "minute"), (1, "second")):
        n, seconds = divmod(seconds, size)
        if n:
            parts.append(f"{n} {unit}" if n == 1 else f"{n} {unit}s")
    if parts == ["1 hour"] or parts == ["1 minute"]:
        return parts[0][2:]
    return (
        " and ".join(parts)
        if len(parts) < 3
        else f"{parts[0]}, {parts[1]} and {parts[2]}"
    )


def timeago_filter(value):
    value = ensure_tz(value)
    if value is None:
        return "Never"
    secs = int((datetime.now(timezone.utc) - value).total_seconds())
    return f"in {span(-secs)}" if secs < 0 else f"{span(secs)} ago"


def timeuntil_filter(value):
    value = ensure_tz(value)
    if value is None:
        return "Never"
    secs = int((value - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "due now"
    return f"in {span(secs)}"


def to_iso_filter(value):
    value = ensure_tz(value)
    if value is None:
        return ""
    return value.isoformat()


def is_recent_filter(value, hours=1):
    value = ensure_tz(value)
    if value is None:
        return False
    return (datetime.now(timezone.utc) - value).total_seconds() < hours * 3600


def _diff_side(mod, text):
    inner = "" if text is None else html_module.escape(text)
    return f'<div class="diff__side diff__side--{mod}">{inner}</div>'


def _diff_pair(left, right, lmod, rmod):
    return f'<div class="diff__row">{_diff_side(lmod, left)}{_diff_side(rmod, right)}</div>'


def diff_html_filter(diff_text):
    if not diff_text:
        return Markup("")
    parts = []
    dels = []
    adds = []

    def flush():
        for i in range(max(len(dels), len(adds))):
            left = dels[i] if i < len(dels) else None
            right = adds[i] if i < len(adds) else None
            parts.append(
                _diff_pair(
                    left,
                    right,
                    "del" if left is not None else "blank",
                    "add" if right is not None else "blank",
                )
            )
        dels.clear()
        adds.clear()

    for line in diff_text.splitlines():
        if line.startswith("@"):
            flush()
            parts.append(f'<div class="diff__hunk">{html_module.escape(line)}</div>')
        elif line.startswith("+"):
            adds.append(line[1:])
        elif line.startswith("-"):
            dels.append(line[1:])
        elif line.startswith("\\ "):
            flush()
            parts.append(_diff_pair(line, line, "meta", "meta"))
        else:
            flush()
            text = line[1:] if line.startswith(" ") else line
            parts.append(_diff_pair(text, text, "ctx", "ctx"))
    flush()
    return Markup(f'<div class="diff diff--split">{"".join(parts)}</div>')


FILTERS = {
    "strftime": strftime_filter,
    "duration": duration_filter,
    "timeago": timeago_filter,
    "timeuntil": timeuntil_filter,
    "to_iso": to_iso_filter,
    "is_recent": is_recent_filter,
    "diff_html": diff_html_filter,
}


def register_filters(app):
    for name, fn in FILTERS.items():
        app.template_filter(name)(fn)
