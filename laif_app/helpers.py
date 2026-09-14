import os
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import current_app, flash, redirect, request, session, url_for

from config import (
    IMAGE_EXTENSIONS,
    LINK_SCHEMES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_SOURCE_BYTES,
    MAX_VIDEO_BYTES,
    MEDIA_EXTENSIONS,
    RESOURCE_EXTENSIONS,
    UPLOAD_DIR,
    VIDEO_EXTENSIONS,
)
from laif_app.extensions import db
from laif_app.models import User


def current_user():
    """The signed-in account, or None.

    A suspended account reads as signed out even if its session cookie is
    still valid, so deactivating someone takes effect on their next click
    rather than whenever they happen to log out.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if user and not user.active:
        return None
    return user


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user.role != "admin":
            flash("Please sign in with an admin account.", "error")
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "error")
            return redirect(url_for("user.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def file_extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def allowed_resource_file(filename):
    return file_extension(filename) in RESOURCE_EXTENSIONS


def media_kind(filename):
    """Return "image", "video" or None for the given upload name."""
    ext = file_extension(filename)
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def upload_size(storage):
    """Byte length of an uploaded file, leaving the stream ready to save."""
    storage.stream.seek(0, os.SEEK_END)
    size = storage.stream.tell()
    storage.stream.seek(0)
    return size


def save_media(storage, kinds=("image", "video")):
    """Validate and store an upload. Returns (kind, filename, error_message)."""
    if not storage or not storage.filename:
        return None, None, "Please choose a file to upload."

    kind = media_kind(storage.filename)
    if kind not in kinds:
        allowed = sorted(MEDIA_EXTENSIONS if len(kinds) > 1 else IMAGE_EXTENSIONS)
        return None, None, "Unsupported file type. Accepted formats: " + ", ".join(allowed) + "."

    # An image that is about to be re-encoded may arrive much larger than it
    # will be stored, so the ceiling depends on whether optimising is possible.
    if kind == "image":
        limit = MAX_IMAGE_SOURCE_BYTES if optimization_active() else MAX_IMAGE_BYTES
    else:
        limit = MAX_VIDEO_BYTES
    if upload_size(storage) > limit:
        return None, None, f"That {kind} is larger than {limit // (1024 * 1024)}MB. Please upload a smaller file."

    filename = f"{secrets.token_hex(8)}.{file_extension(storage.filename)}"
    storage.save(os.path.join(UPLOAD_DIR, filename))
    if kind == "image":
        optimize_upload(filename)
    return kind, filename, None


def delete_upload(filename):
    """Remove a stored upload, ignoring files that have already gone."""
    if not filename:
        return
    try:
        os.remove(os.path.join(UPLOAD_DIR, filename))
    except OSError:
        pass


def normalize_link(raw):
    """Tidy a member-supplied website or social handle into a safe URL.

    Members type things like "instagram.com/laif" or "@laif" as often as they
    paste a full address, so a missing scheme is filled in with https. Anything
    that is not plain http(s) — a javascript: or data: payload, say — is
    refused rather than stored. Returns (url, error_message).
    """
    value = (raw or "").strip()
    if not value:
        return None, "Please paste a website address or social media link."

    if "://" not in value:
        # A lone handle has no host to link to, so ask for the full address.
        if value.startswith("@") or "." not in value.split("/", 1)[0]:
            return None, "Please include the full address, e.g. instagram.com/your-handle."
        value = "https://" + value

    parts = urlsplit(value)
    if parts.scheme.lower() not in LINK_SCHEMES or not parts.netloc:
        return None, "Only http:// and https:// links can be added."
    if len(value) > 500:
        return None, "That link is too long."
    return value, None


# ---------------------------------------------------------------------------
# Re-encoding photographs as they arrive
# ---------------------------------------------------------------------------
#
# A picture straight off a phone or camera is several megabytes, and serving it
# untouched is what makes a site feel slow. Every uploaded image is resized and
# re-encoded here, on the way in, so nobody has to remember to do it first.
#
# Pillow is the one dependency this needs. If it is missing — an install that
# failed on the host, say — uploads carry on working and are simply stored as
# they arrived: a slow picture is better than a refused one.

try:
    from PIL import Image, ImageOps
    PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the host's install
    PILLOW_AVAILABLE = False


# Formats where more than one frame means animation, rather than a camera
# packing a preview alongside the photograph.
ANIMATED_FORMATS = {"GIF", "WEBP", "PNG", "APNG"}


def optimization_active():
    """True when an uploaded picture will actually be re-encoded."""
    return PILLOW_AVAILABLE and current_app.config.get("OPTIMIZE_UPLOADS", True)


def optimize_upload(filename):
    """Re-encode a stored upload in place. Returns (saved_bytes, error).

    `saved_bytes` is 0 when the file was already small enough to leave alone.
    Never raises: a picture that cannot be read is left exactly as it is.
    """
    if not current_app.config.get("OPTIMIZE_UPLOADS", True):
        return 0, None
    if not PILLOW_AVAILABLE:
        return 0, "Pillow is not installed"
    if media_kind(filename) != "image":
        return 0, None

    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        return 0, "file not found"

    before = os.path.getsize(path)
    extension = file_extension(filename)
    max_edge = current_app.config.get("UPLOAD_MAX_EDGE", 2400)

    try:
        with Image.open(path) as image:
            # An animated GIF or WebP would lose every frame but the first, so
            # it is left alone. Only those formats animate: a camera JPEG is
            # often an MPO carrying a second embedded frame, and skipping
            # those would skip the very pictures most worth re-encoding.
            if image.format in ANIMATED_FORMATS and getattr(image, "n_frames", 1) > 1:
                return 0, None

            # The camera's rotation flag is applied to the pixels, then
            # dropped with the rest of the metadata. Stripping it without
            # turning the image would lay the picture on its side.
            image = ImageOps.exif_transpose(image)
            if max(image.size) > max_edge:
                image.thumbnail((max_edge, max_edge), Image.LANCZOS)

            # Written beside the original so a failure half-way through
            # cannot leave a truncated file where the upload used to be.
            staged = path + ".opt"
            if extension in {"jpg", "jpeg"}:
                # MPO and similar camera containers save down to a plain JPEG.
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image.save(staged, "JPEG",
                           quality=current_app.config.get("UPLOAD_JPEG_QUALITY", 82),
                           optimize=True, progressive=True)
            elif extension == "png":
                # A photograph saved as PNG is megabytes; a 256-colour palette
                # takes most of that off at an error invisible on a photo, and
                # quantising in RGBA keeps any transparency.
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "A" in image.mode else "RGB")
                image.quantize(colors=current_app.config.get("UPLOAD_PNG_COLOURS", 256),
                               method=Image.FASTOCTREE,
                               dither=Image.FLOYDSTEINBERG).save(staged, "PNG", optimize=True)
            elif extension == "webp":
                image.save(staged, "WEBP",
                           quality=current_app.config.get("UPLOAD_JPEG_QUALITY", 82),
                           method=4)
            else:
                return 0, None
    except Exception as exc:  # noqa: BLE001 - a bad picture must not lose an upload
        current_app.logger.warning("Could not optimise %s: %s", filename, exc)
        _discard(path + ".opt")
        return 0, str(exc)

    after = os.path.getsize(staged)
    # Small or already-efficient files can come out larger; keep the smaller one.
    if after >= before:
        _discard(staged)
        return 0, None

    try:
        os.replace(staged, path)
    except OSError as exc:
        current_app.logger.warning("Could not replace %s after optimising: %s", filename, exc)
        _discard(staged)
        return 0, str(exc)
    return before - after, None


def _discard(path):
    try:
        os.remove(path)
    except OSError:
        pass


def human_size(byte_count):
    """A rounded size for a flash message: 1.4MB, 820KB, 12 bytes."""
    if byte_count >= 1024 * 1024:
        return f"{byte_count / 1024 / 1024:.1f}MB"
    if byte_count >= 1024:
        return f"{byte_count / 1024:.0f}KB"
    return f"{byte_count} bytes"
