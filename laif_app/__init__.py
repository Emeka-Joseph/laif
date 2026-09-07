from datetime import datetime

from flask import Flask, flash, redirect, request, url_for

from config import Config
from laif_app.extensions import db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from laif_app.admin import admin_bp
    from laif_app.user import user_bp

    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)

    from laif_app.helpers import current_user

    @app.context_processor
    def inject_globals():
        return {"current_user": current_user(), "year": datetime.utcnow().year}

    @app.errorhandler(413)
    def upload_too_large(error):
        # Flask aborts the request before any view runs, so answer here rather
        # than letting the member meet a bare error page.
        flash("That file is too large to upload. Please choose a smaller one.", "error")
        return redirect(request.referrer or url_for("user.home")), 302

    with app.app_context():
        from laif_app.seed import seed

        seed()

    return app
