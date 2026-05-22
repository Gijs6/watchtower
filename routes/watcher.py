from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import Site, Snapshot, db
from utils.watcher import get_setting, set_setting


watcher_bp = Blueprint("watcher", __name__, url_prefix="/watcher")


@watcher_bp.get("/")
def index():
    return render_template("watcher/index.jinja")


@watcher_bp.get("/island")
def island():
    sites = Site.query.order_by(Site.name).all()
    latest = {
        site.id: Snapshot.query.filter_by(site_id=site.id)
        .order_by(Snapshot.captured_at.desc())
        .first()
        for site in sites
    }
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    timeline = {}
    for site in sites:
        buckets = [None] * 24
        snaps = Snapshot.query.filter(
            Snapshot.site_id == site.id,
            Snapshot.captured_at >= cutoff,
        ).all()
        for snap in snaps:
            ts = snap.captured_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bucket = 23 - int((now - ts).total_seconds() / 3600)
            if 0 <= bucket < 24:
                if buckets[bucket] is None:
                    buckets[bucket] = 0
                if snap.changed:
                    buckets[bucket] += 1
        timeline[site.id] = buckets
    return render_template(
        "watcher/islands/sites.jinja", sites=sites, latest=latest, timeline=timeline
    )


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
        interval = max(60, int(interval))
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
        site.check_interval = max(60, int(interval))
    except ValueError:
        pass
    db.session.commit()
    flash(f"Updated {site.name}.", "success")
    return redirect(url_for("watcher.detail", site_id=site.id))


@watcher_bp.get("/sites/<site_id>")
def detail(site_id):
    site = db.get_or_404(Site, site_id)
    snapshots = (
        Snapshot.query.filter_by(site_id=site.id)
        .order_by(Snapshot.captured_at.desc())
        .limit(50)
        .all()
    )
    return render_template("watcher/site.jinja", site=site, snapshots=snapshots)


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
