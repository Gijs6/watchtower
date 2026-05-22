import os

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from models import db
from routes import register_routes
from utils.filters import register_filters
from utils.watcher import start_worker


load_dotenv(override=True)

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", os.urandom(100).hex())
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DB_URI", "sqlite:///watchtower.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
register_filters(app)
register_routes(app)

os.makedirs(app.instance_path, exist_ok=True)

with app.app_context():
    db.create_all()

if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_worker(app)


def is_logged_in():
    return session.get("authenticated") is True


@app.route("/")
def index():
    if not is_logged_in():
        return redirect(url_for("login"))
    return redirect(url_for("watcher.index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if is_logged_in():
        return redirect(url_for("index"))
    if request.method == "POST":
        password = request.form.get("password", "")
        stored_hash = os.getenv("PASSWORD_HASH", "")
        if stored_hash and check_password_hash(stored_hash, password):
            session["authenticated"] = True
            return redirect(url_for("index"))
        flash("Incorrect password.", "error")
    return render_template("login.jinja")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.context_processor
def inject_globals():
    from utils.watcher import get_setting
    return {"discord_webhook_set": bool(get_setting("discord_webhook", ""))}


@app.before_request
def require_login():
    allowed = {"login", "logout", "static"}
    if request.endpoint and request.endpoint not in allowed:
        if not is_logged_in():
            return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
