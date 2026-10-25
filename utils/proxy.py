import socket
import time

from werkzeug.middleware.proxy_fix import ProxyFix

RESOLVE_EVERY = 60


class TrustedProxyFix:
    def __init__(self, app, proxies):
        self.app = app
        self.fixed = ProxyFix(app, x_for=1, x_proto=1, x_host=1)
        self.proxies = proxies
        self.addresses = set()
        self.resolved_at = 0.0

    def trusted(self):
        if self.addresses and time.monotonic() - self.resolved_at < RESOLVE_EVERY:
            return self.addresses
        addresses = set()
        for proxy in self.proxies:
            try:
                addresses |= {info[4][0] for info in socket.getaddrinfo(proxy, None)}
            except OSError:
                continue
        self.addresses = addresses
        self.resolved_at = time.monotonic()
        return addresses

    def __call__(self, environ, start_response):
        if self.proxies and environ.get("REMOTE_ADDR") in self.trusted():
            return self.fixed(environ, start_response)
        for key in [k for k in environ if k.startswith("HTTP_X_FORWARDED_")]:
            del environ[key]
        return self.app(environ, start_response)
