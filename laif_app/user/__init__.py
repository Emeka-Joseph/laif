from flask import Blueprint

user_bp = Blueprint("user", __name__, template_folder="templates")

from laif_app.user import routes  # noqa: E402,F401
