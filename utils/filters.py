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


def diff_html_filter(diff_text):
    if not diff_text:
        return Markup("")
    parts = []
    for line in diff_text.splitlines():
        if line.startswith("+"):
            gutter = "+"
            content = html_module.escape(line[1:])
            parts.append(
                f'<span class="diff-line diff-line--added">'
                f'<span class="diff-line__gutter">{gutter}</span>'
                f'<span class="diff-line__content">{content}</span>'
                f"</span>"
            )
        elif line.startswith("-"):
            gutter = "-"
            content = html_module.escape(line[1:])
            parts.append(
                f'<span class="diff-line diff-line--removed">'
                f'<span class="diff-line__gutter">{gutter}</span>'
                f'<span class="diff-line__content">{content}</span>'
                f"</span>"
            )
        elif line.startswith("@"):
            content = html_module.escape(line)
            parts.append(f'<span class="diff-line diff-line--hunk">{content}</span>')
        elif line.startswith("\\ "):
            content = html_module.escape(line)
            parts.append(
                f'<span class="diff-line diff-line--truncated">{content}</span>'
            )
        else:
            gutter = " "
            content = html_module.escape(line[1:] if line.startswith(" ") else line)
            parts.append(
                f'<span class="diff-line diff-line--context">'
                f'<span class="diff-line__gutter">{gutter}</span>'
                f'<span class="diff-line__content">{content}</span>'
                f"</span>"
            )
    return Markup("\n".join(parts))


FILTERS = {
    "strftime": strftime_filter,
    "timeago": timeago_filter,
    "to_iso": to_iso_filter,
    "diff_html": diff_html_filter,
}


def register_filters(app):
    for name, fn in FILTERS.items():
        app.template_filter(name)(fn)
