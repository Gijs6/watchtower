import os

from dotenv import load_dotenv
from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db
from routes import register_routes
from utils.auth import init_auth
from utils.errors import register_errors
from utils.filters import register_filters
from utils.toasts import register_toasts
from utils.version import register_version
from utils.watcher import start_worker


load_dotenv(override=True)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.secret_key = os.getenv("SECRET_KEY", os.urandom(100).hex())
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DB_URI", "sqlite:///watchtower.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
init_auth(app)
register_filters(app)
register_routes(app)
register_toasts(app)
register_version(app, "radar")
register_errors(app, "radar")

os.makedirs(app.instance_path, exist_ok=True)

with app.app_context():
    db.create_all()

if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_worker(app)


app.add_url_rule("/", "index", app.view_functions["watcher.index"])


@app.context_processor
def inject_globals():
    from datetime import datetime, timezone

    from models import Snapshot
    from utils.watcher import get_setting

    webhook_set = bool(get_setting("discord_webhook", ""))

    last_seen_str = get_setting("notifications_last_seen")
    if last_seen_str:
        try:
            last_seen = datetime.fromisoformat(last_seen_str)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            notification_count = Snapshot.query.filter(
                Snapshot.changed == True,
                Snapshot.captured_at > last_seen,
            ).count()
        except Exception:
            notification_count = 0
    else:
        notification_count = Snapshot.query.filter(Snapshot.changed == True).count()

    return {
        "discord_webhook_set": webhook_set,
        "notification_count": notification_count,
    }


@app.errorhandler(403)
def forbidden(_e):
    return render_template(
        "error.jinja",
        code=403,
        title="Forbidden",
        description="You don't have permission to view this page.",
    ), 403


@app.errorhandler(404)
def not_found(_e):
    return render_template(
        "error.jinja",
        code=404,
        title="Not found",
        description="The page you're looking for doesn't exist.",
    ), 404


@app.errorhandler(500)
def server_error(_e):
    return render_template(
        "error.jinja",
        code=500,
        title="Server error",
        description="Something went wrong on our end. Try again later.",
    ), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000, debug=True)
