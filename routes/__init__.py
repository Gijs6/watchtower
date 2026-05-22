from .watcher import watcher_bp


def register_routes(app):
    app.register_blueprint(watcher_bp)
