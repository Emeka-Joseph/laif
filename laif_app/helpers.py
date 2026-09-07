import os
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import flash, redirect, request, session, url_for

from config import (
    IMAGE_EXTENSIONS,
    LINK_SCHEMES,
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
    MEDIA_EXTENSIONS,
    RESOURCE_EXTENSIONS,
    UPLOAD_DIR,
    VIDEO_EXTENSIONS,
)
from laif_app.extensions import db
from laif_app.models import User


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


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

    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
    if upload_size(storage) > limit:
        return None, None, f"That {kind} is larger than {limit // (1024 * 1024)}MB. Please upload a smaller file."

    filename = f"{secrets.token_hex(8)}.{file_extension(storage.filename)}"
    storage.save(os.path.join(UPLOAD_DIR, filename))
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
