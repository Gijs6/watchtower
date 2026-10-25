import ipaddress
import os
import time
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import requests
from authlib.integrations.flask_client import OAuth, OAuthError
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from utils.toasts import htmx_redirect

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()

RECHECK_EVERY = timedelta(minutes=10)


def provider():
    return current_app.config["AUTH_PROVIDER"]


def home_url(**kwargs):
    return url_for(current_app.config["AUTH_HOME"], **kwargs)


def local_target(target):
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    if any(ord(c) <= 0x20 or ord(c) == 0x7F or c == "\\" for c in target):
        return None
    return target


def session_age():
    signed_in_at = session.get("signed_in_at")
    if signed_in_at is None:
        return None
    return timedelta(seconds=time.time() - signed_in_at)


def dev_login():
    try:
        ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return current_app.debug and ip.is_loopback


def is_logged_in():
    if session.get("authenticated") is not True:
        return False
    if provider() == "password":
        return True
    age = session_age()
    return age is not None and age < current_app.config["OIDC_SESSION_LIFETIME"]


def still_signed_in():
    if provider() != "oidc" or dev_login():
        return True
    if time.time() - session.get("checked_at", 0) < RECHECK_EVERY.total_seconds():
        return True
    endpoint = oauth.oidc.load_server_metadata().get("userinfo_endpoint")
    try:
        response = requests.get(
            endpoint,
            headers={"Authorization": f"Bearer {session.get('access_token', '')}"},
            timeout=5,
        )
    except requests.RequestException as error:
        current_app.logger.warning("Couldn't reach the OIDC provider: %s", error)
        return True
    if response.status_code in (401, 403):
        return False
    session["checked_at"] = time.time()
    return True


def sign_in(user=None, id_token=None, access_token=None):
    session.clear()
    session.permanent = True
    session["authenticated"] = True
    session["signed_in_at"] = time.time()
    session["checked_at"] = time.time()
    if user:
        session["user"] = user
    if id_token:
        session["id_token"] = id_token
    if access_token:
        session["access_token"] = access_token


def same_host_path(url):
    parts = urlsplit(url)
    if parts.netloc != request.host:
        return None
    return urlunsplit(("", "", parts.path, parts.query, ""))


def login_url():
    if request.headers.get("HX-Request"):
        target = same_host_path(request.headers.get("HX-Current-URL", ""))
    elif request.method == "GET":
        target = request.full_path.rstrip("?")
    else:
        target = same_host_path(request.headers.get("Referer", ""))
    return url_for("auth.login", next=target)


def check_password(form):
    stored_hash = os.getenv("PASSWORD_HASH", "")
    return bool(stored_hash) and check_password_hash(
        stored_hash, form.get("password", "")
    )


def require_login():
    if (
        dev_login()
        and provider() == "password"
        and not is_logged_in()
        and not session.get("dev_signed_out")
    ):
        sign_in()
    endpoint = request.endpoint
    if (
        endpoint is None
        or endpoint == "static"
        or endpoint.startswith("auth.")
        or endpoint in current_app.config["AUTH_PUBLIC"]
    ):
        return None
    scope = current_app.config["AUTH_SCOPE"]
    if scope and request.blueprint != scope:
        return None
    if not is_logged_in():
        return htmx_redirect(login_url())
    if not still_signed_in():
        session.clear()
        return htmx_redirect(login_url())
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = local_target(request.values.get("next")) or home_url()
    if provider() == "oidc":
        if is_logged_in():
            return redirect(next_url)
        session["next"] = next_url
        return oauth.oidc.authorize_redirect(url_for("auth.callback", _external=True))
    if is_logged_in():
        return redirect(next_url)
    if request.method == "POST":
        if dev_login() or current_app.extensions["auth_check"](request.form):
            sign_in()
            return redirect(next_url)
        if "code" in request.form:
            flash("Incorrect password or code.", "error")
        else:
            flash("Incorrect password.", "error")
    return render_template("login.jinja", next_url=next_url)


@auth_bp.get("/auth/callback")
def callback():
    if provider() != "oidc":
        abort(404)
    next_url = session.get("next") or home_url()
    try:
        token = oauth.oidc.authorize_access_token()
    except OAuthError as error:
        current_app.logger.warning("OIDC sign-in failed: %s", error)
        abort(403)
    claims = token.get("userinfo") or {}
    user = claims.get(current_app.config["OIDC_USER_CLAIM"])
    if not user or str(user) not in current_app.config["OIDC_ALLOWED_USERS"]:
        current_app.logger.warning("OIDC user %r isn't allowed", user)
        abort(403)
    sign_in(str(user), token.get("id_token"), token.get("access_token"))
    return redirect(next_url)


@auth_bp.post("/logout")
def logout():
    id_token = session.get("id_token")
    session.clear()
    if current_app.debug:
        session["dev_signed_out"] = True
    if provider() == "oidc":
        metadata = oauth.oidc.load_server_metadata()
        if metadata.get("end_session_endpoint"):
            return oauth.oidc.logout_redirect(
                post_logout_redirect_uri=home_url(_external=True),
                id_token_hint=id_token,
                client_id=oauth.oidc.client_id,
            )
    return redirect(url_for("auth.login"))


def init_auth(app, home="index", public=(), scope=None, check=None):
    auth_provider = os.getenv("AUTH_PROVIDER", "password")
    if auth_provider not in ("password", "oidc"):
        raise RuntimeError("AUTH_PROVIDER must be 'password' or 'oidc'")
    app.config["AUTH_PROVIDER"] = auth_provider
    app.config["AUTH_HOME"] = home
    app.config["AUTH_PUBLIC"] = set(public)
    app.config["AUTH_SCOPE"] = scope
    app.extensions["auth_check"] = check or check_password
    if auth_provider == "oidc":
        issuer = os.getenv("OIDC_ISSUER", "").rstrip("/")
        client_id = os.getenv("OIDC_CLIENT_ID", "")
        if not issuer or not client_id:
            raise RuntimeError("OIDC_ISSUER and OIDC_CLIENT_ID must be set")
        allowed = {u.strip() for u in os.getenv("OIDC_ALLOWED_USERS", "").split(",")}
        app.config["OIDC_ALLOWED_USERS"] = allowed - {""}
        app.config["OIDC_USER_CLAIM"] = os.getenv("OIDC_USER_CLAIM", "sub")
        app.config["OIDC_SESSION_LIFETIME"] = timedelta(
            minutes=int(os.getenv("OIDC_SESSION_MINUTES", "60"))
        )
        app.config["PERMANENT_SESSION_LIFETIME"] = app.config["OIDC_SESSION_LIFETIME"]
        client_secret = os.getenv("OIDC_CLIENT_SECRET") or None
        oauth.init_app(app)
        oauth.register(
            "oidc",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=f"{issuer}/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid profile email",
                "code_challenge_method": "S256",
                "token_endpoint_auth_method": (
                    "client_secret_basic" if client_secret else "none"
                ),
            },
        )
    app.register_blueprint(auth_bp, url_prefix=f"/{scope}" if scope else None)
    app.before_request(require_login)
    app.jinja_env.globals["auth_provider"] = auth_provider
