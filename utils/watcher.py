import difflib
import hashlib
import threading
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from models import Setting, Site, Snapshot, db


worker_thread = None
worker_lock = threading.Lock()

CONTENT_MAX_LEN = 50000
SNAPSHOT_LIMIT = 50
CHECK_LOOP_INTERVAL = 10


def get_setting(key, default=None):
    s = db.session.get(Setting, key)
    return s.value if s else default


def set_setting(key, value):
    s = db.session.get(Setting, key)
    if s is None:
        s = Setting(key=key, value=value)
        db.session.add(s)
    else:
        s.value = value
    db.session.commit()


def extract_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def fetch_page(url):
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Watchtower/1.0 change-monitor"},
        )
        content_type = resp.headers.get("Content-Type", "")
        is_text = content_type.startswith("text/")
        return resp.text, is_text, None
    except Exception as e:
        return None, False, str(e)[:200]


def compute_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def compute_diff_snippet(old_text, new_text, max_lines=50):
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, n=3))
    diff = diff[2:] if len(diff) > 2 else diff
    if not diff:
        return None
    snippet = []
    for line in diff:
        snippet.append(line.rstrip("\n"))
        if len(snippet) >= max_lines:
            snippet.append("\\ ...")
            break
    return "\n".join(snippet)


def do_check(site):
    now = datetime.now(timezone.utc)
    html_content, is_text, error = fetch_page(site.url)

    if error:
        db.session.add(
            Snapshot(
                site_id=site.id,
                captured_at=now,
                content_hash="",
                content=None,
                changed=False,
                diff_snippet=None,
                error=error,
            )
        )
        site.last_checked_at = now
        db.session.commit()
        return

    text = (
        extract_text(html_content)[:CONTENT_MAX_LEN]
        if is_text
        else html_content[:CONTENT_MAX_LEN]
    )
    content_hash = compute_hash(text)

    prev = (
        Snapshot.query.filter_by(site_id=site.id)
        .filter(Snapshot.error.is_(None))
        .order_by(Snapshot.captured_at.desc())
        .first()
    )

    changed = prev is not None and prev.content_hash != content_hash
    diff_snippet = (
        compute_diff_snippet(prev.content, text)
        if changed and prev.content and is_text
        else "Diff not available."
        if changed
        else None
    )

    db.session.add(
        Snapshot(
            site_id=site.id,
            captured_at=now,
            content_hash=content_hash,
            content=text,
            changed=changed,
            diff_snippet=diff_snippet,
            error=None,
        )
    )
    site.last_checked_at = now
    if changed:
        site.last_changed_at = now
    db.session.commit()

    old_snaps = (
        Snapshot.query.filter_by(site_id=site.id)
        .order_by(Snapshot.captured_at.desc())
        .offset(SNAPSHOT_LIMIT)
        .all()
    )
    for old in old_snaps:
        db.session.delete(old)
    db.session.commit()

    if changed:
        webhook_url = get_setting("discord_webhook")
        if webhook_url:
            from utils.discord import send_notification

            send_notification(webhook_url, site, now, diff_snippet)


def run_worker(app):
    while True:
        try:
            with app.app_context():
                now = datetime.now(timezone.utc)
                for site in Site.query.filter_by(is_active=True).all():
                    last = (
                        Snapshot.query.filter_by(site_id=site.id)
                        .order_by(Snapshot.captured_at.desc())
                        .first()
                    )
                    last_at = last.captured_at if last else None
                    if last_at is not None and last_at.tzinfo is None:
                        last_at = last_at.replace(tzinfo=timezone.utc)
                    if (
                        last_at is None
                        or (now - last_at).total_seconds() >= site.check_interval
                    ):
                        do_check(site)
        except Exception as e:
            print(f"Worker error: {e}")
        time.sleep(CHECK_LOOP_INTERVAL)


def start_worker(app):
    global worker_thread
    with worker_lock:
        if worker_thread is None or not worker_thread.is_alive():
            worker_thread = threading.Thread(
                target=run_worker, args=(app,), daemon=True
            )
            worker_thread.start()
