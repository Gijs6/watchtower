import secrets
import string
from datetime import datetime, timedelta, timezone

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

    @property
    def next_check_at(self):
        if not self.is_active:
            return None
        if self.last_checked_at is None:
            return datetime.now(timezone.utc)
        last = self.last_checked_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last + timedelta(seconds=self.check_interval)

    def status(self, latest):
        if not self.is_active:
            return "paused"
        if latest is None:
            return "pending"
        if latest.error:
            return "down"
        return "up"


class Snapshot(db.Model):
    id = db.Column(db.String(16), primary_key=True, default=generate_id)
    site_id = db.Column(db.String(16), db.ForeignKey("site.id"), nullable=False)
    captured_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    content_hash = db.Column(db.String(64), nullable=False, default="")
    content = db.Column(db.Text, nullable=True)
    changed = db.Column(db.Boolean, nullable=False, default=False)
    diff_snippet = db.Column(db.Text, nullable=True)
    error = db.Column(db.String, nullable=True)

    @property
    def outcome(self):
        if self.error:
            return "error"
        if self.changed:
            return "changed"
        return "unchanged"


class Setting(db.Model):
    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.Text, nullable=True)
