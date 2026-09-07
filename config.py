import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
UPLOAD_DIR = os.path.join(BASE_DIR, "laif_app", "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

RESOURCE_CATEGORIES = ["E-books", "Study guides", "Sermons", "Family & life"]
RESOURCE_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "epub", "mp3", "mp4", "zip"}

# Portfolio media: photographs and short clips of a member's previous work.
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 60 * 1024 * 1024
MAX_PORTFOLIO_ITEMS = 40

# A member's previous work is grouped into jobs; each job carries its own
# gallery and its own set of links out to a website or social media handle.
MAX_PORTFOLIO_WORKS = 20
MAX_WORK_MEDIA = 15
MAX_WORK_LINKS = 8

# A member's own website and social media handles, shown on their profile
# beside their contact details.
MAX_MEMBER_LINKS = 8

# Schemes a member may link out with. Anything else is rejected, and a bare
# host such as "instagram.com/name" is upgraded to https:// on the way in.
LINK_SCHEMES = {"http", "https"}

# One-time passcodes guarding profile changes.
OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 45

_DB_USER = os.environ.get("LAIF_DB_USER", "root")
_DB_PASSWORD = os.environ.get("LAIF_DB_PASSWORD", "")
_DB_HOST = os.environ.get("LAIF_DB_HOST", "localhost")
_DB_PORT = os.environ.get("LAIF_DB_PORT", "3306")
_DB_NAME = os.environ.get("LAIF_DB_NAME", "laifdb")


def _flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("LAIF_SECRET_KEY", "laif-community-dev-key")
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = UPLOAD_DIR
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024

    # Email delivery for one-time passcodes. With no SMTP host configured the
    # code is written to the application log and shown on the verify screen,
    # which keeps local development workable without a mail server.
    SMTP_HOST = os.environ.get("LAIF_SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("LAIF_SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("LAIF_SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("LAIF_SMTP_PASSWORD", "")
    SMTP_USE_TLS = _flag("LAIF_SMTP_TLS", "1")
    MAIL_SENDER = os.environ.get("LAIF_MAIL_SENDER", "laifoffice2020@gmail.com")

    # Show the passcode in the browser when no mail server is wired up.
    OTP_SHOW_IN_UI = _flag("LAIF_OTP_SHOW_IN_UI", "1")
