"""Entry point for cPanel's "Setup Python App" (Phusion Passenger).

Passenger imports this file and serves the WSGI callable named ``application``.
The interpreter is already the virtualenv cPanel made for the application, so
nothing here activates one.

Every setting comes from the environment variables entered in the cPanel
Python App screen; ``check_deploy.py`` verifies them before you go live.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import DEFAULT_ADMIN_PASSWORD, DEV_SECRET_KEY  # noqa: E402
from laif_app import create_app  # noqa: E402

application = create_app()

# Loud in the log rather than fatal: a site that boots and complains is easier
# to rescue than one that refuses to start with a blank page.
if application.config["SECRET_KEY"] == DEV_SECRET_KEY:
    application.logger.warning(
        "LAIF_SECRET_KEY is unset, so sessions are signed with the key published "
        "in the repository. Anyone can forge a login cookie until this is fixed."
    )
if application.config["ADMIN_PASSWORD"] == DEFAULT_ADMIN_PASSWORD:
    application.logger.warning(
        "LAIF_ADMIN_PASSWORD is unset. The administrator account is using the "
        "default password published in the repository."
    )
if application.config["OTP_SHOW_IN_UI"]:
    application.logger.warning(
        "LAIF_OTP_SHOW_IN_UI is on. Passcodes will be displayed in the browser "
        "whenever email delivery fails. Set it to 0 on a public server."
    )
