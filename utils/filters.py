import html as html_module
from datetime import datetime, timezone

from markupsafe import Markup


def ensure_tz(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def strftime_filter(value, fmt="%d %b %Y %H:%M"):
    value = ensure_tz(value)
    if value is None:
        return "-"
    return value.strftime(fmt)


def timeago_filter(value):
    value = ensure_tz(value)
    if value is None:
        return "never"
    secs = int((datetime.now(timezone.utc) - value).total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


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
    "timeago": timeago_filter,
    "to_iso": to_iso_filter,
    "is_recent": is_recent_filter,
    "diff_html": diff_html_filter,
}


def register_filters(app):
    for name, fn in FILTERS.items():
        app.template_filter(name)(fn)
