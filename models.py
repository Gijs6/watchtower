import secrets
import string
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def generate_id(length=16):
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


class Site(db.Model):
    id = db.Column(db.String(16), primary_key=True, default=generate_id)
    name = db.Column(db.String, nullable=False)
    url = db.Column(db.String, nullable=False)
    check_interval = db.Column(db.Integer, nullable=False, default=300)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_checked_at = db.Column(db.DateTime, nullable=True)
    last_changed_at = db.Column(db.DateTime, nullable=True)

    snapshots = db.relationship(
        "Snapshot", backref="site", cascade="all, delete-orphan", lazy="dynamic"
    )


class Snapshot(db.Model):
    id = db.Column(db.String(16), primary_key=True, default=generate_id)
    site_id = db.Column(db.String(16), db.ForeignKey("site.id"), nullable=False)
    captured_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    content_hash = db.Column(db.String(64), nullable=False, default="")
    content = db.Column(db.Text, nullable=True)
    changed = db.Column(db.Boolean, nullable=False, default=False)
    diff_snippet = db.Column(db.Text, nullable=True)
    error = db.Column(db.String, nullable=True)


class Setting(db.Model):
    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.Text, nullable=True)
