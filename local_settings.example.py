"""Template for local_settings.py — copy, fill in, keep on the server only.

config.py imports local_settings.py if it exists, so this is an alternative to
entering everything in cPanel's environment-variable screen. An environment
variable of the same name still wins over anything set here.

local_settings.py is listed in .gitignore. This example file carries no real
values and is safe to commit.
"""

# --- Database (cPanel -> MySQL Databases) --------------------------------
LAIF_DB_USER = "cpaneluser_laif"
LAIF_DB_PASSWORD = "the database password"
LAIF_DB_NAME = "cpaneluser_laifdb"
LAIF_DB_HOST = "localhost"
LAIF_DB_PORT = "3306"

# --- Sessions ------------------------------------------------------------
# python -c "import secrets; print(secrets.token_urlsafe(48))"
LAIF_SECRET_KEY = "a long random string, unique to this server"

# --- Administrator seeded on an empty database ---------------------------
LAIF_ADMIN_EMAIL = "office@yourdomain.org"
LAIF_ADMIN_PASSWORD = "a strong password"

# Never show a passcode or a reset link in the browser on a public server.
LAIF_OTP_SHOW_IN_UI = "0"

# --- Mail (cPanel -> Email Accounts) -------------------------------------
LAIF_SMTP_HOST = "mail.yourdomain.org"
LAIF_SMTP_PORT = "465"
LAIF_SMTP_USER = "office@yourdomain.org"
LAIF_SMTP_PASSWORD = "the mailbox password"
LAIF_MAIL_SENDER = "office@yourdomain.org"
