from datetime import datetime

from flask import Flask, flash, redirect, request, url_for

from config import MAX_IMAGE_BYTES, MAX_IMAGE_SOURCE_BYTES, Config
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

    @app.template_filter("first_words")
    def first_words(text, count, suffix="…"):
        """The opening `count` words of a passage, with an ellipsis if cut.

        Used where a card is a summary of something the reader can click
        through to in full. Truncating on words rather than characters means
        a card never ends mid-word.
        """
        words = (text or "").split()
        if len(words) <= count:
            return text
        return " ".join(words[:count]) + suffix

    @app.context_processor
    def inject_globals():
        # Every upload form quotes the size limit, and the limit depends on
        # whether pictures can be re-encoded on arrival, so both are worked
        # out once here rather than passed through each view.
        from laif_app.helpers import optimization_active

        optimizing = optimization_active()
        ceiling = MAX_IMAGE_SOURCE_BYTES if optimizing else MAX_IMAGE_BYTES
        return {
            "current_user": current_user(),
            "year": datetime.utcnow().year,
            "optimizing": optimizing,
            "max_upload_mb": ceiling // (1024 * 1024),
        }

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
