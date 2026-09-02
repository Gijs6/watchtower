from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import Site, Snapshot, db
from sqlalchemy.orm import joinedload
from utils.watcher import get_setting, set_setting


watcher_bp = Blueprint("watcher", __name__, url_prefix="/watcher")

TIMELINE_HOURS = 24


def build_timeline(site, now):
    cutoff = now - timedelta(hours=TIMELINE_HOURS)
    buckets = [None] * TIMELINE_HOURS
    rows = (
        db.session.query(Snapshot.captured_at, Snapshot.error, Snapshot.changed)
        .filter(
            Snapshot.site_id == site.id,
            Snapshot.captured_at >= cutoff,
        )
        .all()
    )
    for snap in rows:
        ts = snap.captured_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        index = (TIMELINE_HOURS - 1) - int((now - ts).total_seconds() / 3600)
        if not 0 <= index < TIMELINE_HOURS:
            continue
        bucket = buckets[index] or {"changes": 0, "errors": 0}
        if snap.error:
            bucket["errors"] += 1
        elif snap.changed:
            bucket["changes"] += 1
        buckets[index] = bucket
    return buckets


def dashboard_data():
    sites = Site.query.order_by(Site.name).all()
    now = datetime.now(timezone.utc)
    latest = {
        site.id: Snapshot.query.filter_by(site_id=site.id)
        .order_by(Snapshot.captured_at.desc())
        .first()
        for site in sites
    }
    status = {site.id: site.status(latest[site.id]) for site in sites}
    timeline = {site.id: build_timeline(site, now) for site in sites}
    return {"sites": sites, "status": status, "timeline": timeline}


@watcher_bp.get("/")
def index():
    return render_template("watcher/index.jinja", **dashboard_data())


@watcher_bp.get("/island")
def island():
    return render_template("watcher/islands/sites.jinja", **dashboard_data())


@watcher_bp.get("/sites/add")
def add_site():
    return render_template("watcher/add_site.jinja")


@watcher_bp.post("/sites")
def add():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    interval = request.form.get("check_interval", "300").strip()
    if not url:
        flash("URL is required.", "error")
        return render_template(
            "watcher/add_site.jinja", name=name, url=url, interval=interval
        )
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not name:
        name = url.removeprefix("https://").removeprefix("http://")
    try:
        interval = max(10, int(interval))
    except ValueError:
        interval = 300
    db.session.add(Site(name=name, url=url, check_interval=interval))
    db.session.commit()
    flash(f"Added {name}.", "success")
    return redirect(url_for("watcher.index"))


@watcher_bp.post("/sites/<site_id>/delete")
def delete(site_id):
    site = db.get_or_404(Site, site_id)
    name = site.name
    db.session.delete(site)
    db.session.commit()
    flash(f"Removed {name}.", "success")
    return redirect(url_for("watcher.index"))


@watcher_bp.post("/sites/<site_id>/toggle")
def toggle(site_id):
    site = db.get_or_404(Site, site_id)
    site.is_active = not site.is_active
    db.session.commit()
    return redirect(url_for("watcher.index"))


@watcher_bp.post("/sites/<site_id>/update")
def update(site_id):
    site = db.get_or_404(Site, site_id)
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    interval = request.form.get("check_interval", "").strip()
    if name:
        site.name = name
    if url:
        site.url = url
    try:
        site.check_interval = max(10, int(interval))
    except ValueError:
        pass
    db.session.commit()
    flash(f"Updated {site.name}.", "success")
    return redirect(url_for("watcher.detail", site_id=site.id))


def squash_snapshots(snapshots):
    """Collapse consecutive runs of the same outcome into one row with a count.

    Each detected change stays on its own row. Consecutive unchanged checks, or
    consecutive errors sharing the same message, are merged and counted.
    """

    def mergeable(first, other):
        if first.outcome != other.outcome or first.outcome == "changed":
            return False
        if first.outcome == "error":
            return first.error == other.error
        return True

    result = []
    i = 0
    while i < len(snapshots):
        snap = snapshots[i]
        count = 1
        while i + count < len(snapshots) and mergeable(snap, snapshots[i + count]):
            count += 1
        result.append((snap, count, snapshots[i + count - 1]))
        i += count
    return result


def history_data(site):
    snapshots = (
        Snapshot.query.filter_by(site_id=site.id)
        .order_by(Snapshot.captured_at.desc())
        .limit(200)
        .all()
    )
    return {"site": site, "snapshots": squash_snapshots(snapshots)}


@watcher_bp.get("/sites/<site_id>")
def detail(site_id):
    site = db.get_or_404(Site, site_id)
    latest = (
        Snapshot.query.filter_by(site_id=site.id)
        .order_by(Snapshot.captured_at.desc())
        .first()
    )
    return render_template(
        "watcher/site.jinja", status=site.status(latest), **history_data(site)
    )


@watcher_bp.get("/sites/<site_id>/history")
def history_island(site_id):
    site = db.get_or_404(Site, site_id)
    return render_template("watcher/islands/history.jinja", **history_data(site))


@watcher_bp.get("/notifications/events")
def events_island():
    events = (
        Snapshot.query.options(joinedload(Snapshot.site))
        .filter(Snapshot.changed == True)
        .order_by(Snapshot.captured_at.desc())
        .limit(50)
        .all()
    )
    return render_template("watcher/islands/events.jinja", events=events)


@watcher_bp.get("/notif-count")
def notif_badge():
    return render_template("watcher/islands/notif_badge.jinja")


@watcher_bp.get("/notifications")
def notifications():
    now = datetime.now(timezone.utc)
    set_setting("notifications_last_seen", now.isoformat())
    events = (
        Snapshot.query.options(joinedload(Snapshot.site))
        .filter(Snapshot.changed == True)
        .order_by(Snapshot.captured_at.desc())
        .limit(50)
        .all()
    )
    return render_template("watcher/notifications.jinja", events=events)


@watcher_bp.get("/settings")
def settings():
    webhook = get_setting("discord_webhook", "")
    return render_template("watcher/settings.jinja", webhook=webhook)


@watcher_bp.post("/settings")
def settings_save():
    webhook = request.form.get("discord_webhook", "").strip()
    set_setting("discord_webhook", webhook)
    flash("Settings saved.", "success")
    return redirect(url_for("watcher.settings"))
