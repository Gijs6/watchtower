import os

THEME = "https://cdn.gijs6.nl"


def content_security_policy():
    form_action = "'self'"
    issuer = os.getenv("OIDC_ISSUER", "").rstrip("/")
    if issuer:
        form_action += f" {issuer}"
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {THEME}",
            f"style-src 'self' 'unsafe-inline' {THEME}",
            f"font-src {THEME}",
            "img-src 'self' data:",
            "connect-src 'self'",
            "object-src 'none'",
            f"form-action {form_action}",
            "frame-ancestors 'none'",
            "base-uri 'none'",
        ]
    )


def register_headers(app):
    policy = content_security_policy()

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("Content-Security-Policy", policy)
        return response
