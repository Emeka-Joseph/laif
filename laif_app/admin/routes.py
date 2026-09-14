import os
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import flash, redirect, render_template, request, session, url_for

from config import (
    GIVING_FIELDS,
    MAX_ALBUM_PHOTOS,
    PROJECT_CATEGORIES,
    PROJECT_STATUSES,
    RESOURCE_CATEGORIES,
    UPLOAD_DIR,
)
from laif_app.admin import admin_bp
from laif_app.extensions import db
from laif_app.helpers import (
    admin_required,
    allowed_resource_file,
    current_user,
    delete_upload,
    save_media,
)
from laif_app.models import (
    AccessCode,
    Comment,
    ContactMessage,
    GalleryAlbum,
    GalleryPhoto,
    PortfolioWork,
    Post,
    Project,
    Resource,
    SiteSetting,
    User,
)


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    user = current_user()
    if user and user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        candidate = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        if (candidate and candidate.role == "admin" and candidate.active
                and candidate.check_password(request.form.get("password", ""))):
            session["user_id"] = candidate.id
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
        flash("Email or password not recognised.", "error")
    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        posts=Post.query.order_by(Post.created_at.desc()).all(),
        messages=ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(15).all(),
        recent_members=User.query.filter_by(role="member").order_by(User.id.desc()).limit(5).all(),
        projects=Project.query.order_by(Project.created_at.desc()).all(),
        albums=GalleryAlbum.query.order_by(GalleryAlbum.created_at.desc()).all(),
        comments=Comment.query.order_by(Comment.created_at.desc()).limit(12).all(),
        stats={
            "members": User.query.filter_by(role="member").count(),
            "posts": Post.query.count(),
            "resources": Resource.query.count(),
            "codes": AccessCode.query.filter_by(kind="member").count(),
            "messages": ContactMessage.query.count(),
            "projects": Project.query.filter_by(status="active").count(),
            "albums": GalleryAlbum.query.count(),
            "suspended": User.query.filter_by(is_active=False).count(),
        },
    )


@admin_bp.route("/codes", methods=["GET", "POST"])
@admin_required
def codes():
    if request.method == "POST":
        quantity = max(1, min(int(request.form.get("quantity", 1)), 25))
        generated = []
        for _ in range(quantity):
            code = secrets.token_hex(4).upper()
            db.session.add(AccessCode(code=code, kind="member"))
            generated.append(code)
        db.session.commit()
        flash("Member codes generated: " + ", ".join(generated), "success")
        return redirect(url_for("admin.codes"))
    return render_template(
        "admin/codes.html",
        codes=AccessCode.query.filter_by(kind="member").order_by(AccessCode.created_at.desc()).all(),
    )


@admin_bp.route("/posts/new", methods=["GET", "POST"])
@admin_required
def new_post():
    if request.method == "POST":
        post = Post(
            title=request.form["title"],
            excerpt=request.form.get("excerpt", ""),
            content=request.form["content"],
            image=request.form.get("image", ""),
            author_id=current_user().id,
        )
        db.session.add(post)
        db.session.commit()
        flash("Your story is now published.", "success")
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/post_form.html", post=None)


@admin_bp.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)
    if request.method == "POST":
        post.title = request.form["title"]
        post.excerpt = request.form.get("excerpt", "")
        post.content = request.form["content"]
        post.image = request.form.get("image", "")
        db.session.commit()
        flash("Post updated.", "success")
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/post_form.html", post=post)


@admin_bp.post("/posts/<int:post_id>/delete")
@admin_required
def delete_post(post_id):
    db.session.delete(db.get_or_404(Post, post_id))
    db.session.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/resources/new", methods=["GET", "POST"])
@admin_required
def new_resource():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", RESOURCE_CATEGORIES[0])
        description = request.form.get("description", "").strip()
        link = request.form.get("link", "").strip()
        upload = request.files.get("file")
        filename = None
        original_name = None
        if upload and upload.filename:
            if not allowed_resource_file(upload.filename):
                flash("That file type is not supported.", "error")
                return render_template("admin/resource_form.html", categories=RESOURCE_CATEGORIES)
            ext = upload.filename.rsplit(".", 1)[1].lower()
            filename = f"{secrets.token_hex(8)}.{ext}"
            upload.save(os.path.join(UPLOAD_DIR, filename))
            original_name = upload.filename
        if not title or (not filename and not link):
            flash("Add a title, then attach a file or paste a link.", "error")
            return render_template("admin/resource_form.html", categories=RESOURCE_CATEGORIES)
        db.session.add(Resource(title=title, category=category, description=description, filename=filename, original_name=original_name, link=link or None))
        db.session.commit()
        flash("Resource published to the library.", "success")
        return redirect(url_for("user.resources"))
    return render_template("admin/resource_form.html", categories=RESOURCE_CATEGORIES)


@admin_bp.post("/resources/<int:resource_id>/delete")
@admin_required
def delete_resource(resource_id):
    resource = db.get_or_404(Resource, resource_id)
    if resource.filename:
        path = os.path.join(UPLOAD_DIR, resource.filename)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(resource)
    db.session.commit()
    flash("Resource removed.", "success")
    return redirect(url_for("user.resources"))


# ---------------------------------------------------------------------------
# Registered members
# ---------------------------------------------------------------------------
#
# Passwords are stored only as a hash and are never read here: nothing in these
# views touches `password_hash`, so there is no screen on which a member's
# password can be seen or recovered. A member who is locked out resets their
# own via /forgot-password.


@admin_bp.route("/members")
@admin_required
def members():
    """Everyone registered on the site, newest account first."""
    search = request.args.get("q", "").strip()
    role = request.args.get("role", "all")
    status = request.args.get("status", "all")

    query = User.query
    if role in {"member", "admin"}:
        query = query.filter_by(role=role)
    if status == "suspended":
        query = query.filter(User.is_active.is_(False))
    elif status == "active":
        query = query.filter(User.is_active.isnot(False))
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(
            User.name.ilike(like),
            User.email.ilike(like),
            User.phone.ilike(like),
            User.skills.ilike(like),
            User.city.ilike(like),
            User.country.ilike(like),
        ))

    return render_template(
        "admin/members.html",
        members=query.order_by(User.id.desc()).all(),
        total=User.query.count(),
        member_count=User.query.filter_by(role="member").count(),
        admin_count=User.query.filter_by(role="admin").count(),
        search=search,
        role=role,
        status=status,
        suspended_count=User.query.filter_by(is_active=False).count(),
    )


@admin_bp.route("/members/<int:user_id>")
@admin_required
def member_detail(user_id):
    """One account in full - everything on file except the password."""
    member = db.get_or_404(User, user_id)
    return render_template(
        "admin/member_detail.html",
        member=member,
        works=member.works,
        links=member.links,
        media_count=len(member.portfolio),
        blocker=_delete_blocker(member),
    )


def _delete_blocker(member):
    """Why this account cannot be removed, or None when it can.

    Deleting an admin risks locking everyone out of the panel, and a member
    who has authored posts would leave those posts without an author, so both
    are refused with an explanation rather than a database error.
    """
    if member.id == current_user().id:
        return "This is your own account. Sign in as another administrator to remove it."
    if member.role == "admin":
        return "Administrator accounts cannot be deleted here, to avoid locking the panel."
    if member.posts:
        count = len(member.posts)
        return (f"This account wrote {count} blog post{'s' if count != 1 else ''}. "
                "Delete or reassign them first, or deactivate the account instead.")
    return None


@admin_bp.post("/members/<int:user_id>/delete")
@admin_required
def delete_member(user_id):
    """Remove an account along with everything it uploaded."""
    member = db.get_or_404(User, user_id)

    blocker = _delete_blocker(member)
    if blocker:
        flash(blocker, "error")
        return redirect(url_for("admin.member_detail", user_id=member.id))

    name = member.name
    # The database cascades the rows; the files they point at are ours to clear.
    delete_upload(member.photo)
    for item in member.portfolio:
        delete_upload(item.filename)

    db.session.delete(member)
    db.session.commit()
    flash(f"{name}'s account and everything they uploaded have been removed.", "success")
    return redirect(url_for("admin.members"))


# ---------------------------------------------------------------------------
# Projects and giving
# ---------------------------------------------------------------------------


def _money(raw):
    """Read a typed amount. Returns (value, error); blank means "not set"."""
    text = (raw or "").strip().replace(",", "").replace(" ", "")
    if not text:
        return None, None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None, "Amounts must be plain numbers, for example 25000 or 1500.50."
    if amount < 0:
        return None, "Amounts cannot be negative."
    if amount >= Decimal("10000000000"):
        return None, "That amount is larger than this field can hold."
    return amount, None


def _read_project(project, form, files):
    """Copy a submitted form onto a project. Returns an error message or None."""
    title = form.get("title", "").strip()
    if not title:
        return "A project needs a title."

    target, error = _money(form.get("target"))
    if error:
        return error
    raised, error = _money(form.get("raised"))
    if error:
        return error

    status = form.get("status", "active")
    if status not in PROJECT_STATUSES:
        status = "active"

    upload = files.get("image")
    if upload and upload.filename:
        _, filename, error = save_media(upload, kinds=("image",))
        if error:
            return error
        delete_upload(project.image)
        project.image = filename
    elif form.get("remove_image"):
        delete_upload(project.image)
        project.image = ""

    project.title = title[:200]
    project.summary = form.get("summary", "").strip()[:400]
    project.description = form.get("description", "").strip()
    project.category = form.get("category", "").strip()[:80]
    project.status = status
    project.currency = (form.get("currency", "").strip() or "KWD")[:10]
    project.target = target
    project.raised = raised
    project.location = form.get("location", "").strip()[:160]
    project.starts_on = form.get("starts_on", "").strip()[:80]
    project.featured = bool(form.get("featured"))
    return None


@admin_bp.route("/projects")
@admin_required
def projects():
    return render_template(
        "admin/projects.html",
        projects=Project.query.order_by(Project.created_at.desc()).all(),
        giving=SiteSetting.all_of([key for key, _ in GIVING_FIELDS]),
        giving_fields=GIVING_FIELDS,
    )


@admin_bp.route("/projects/new", methods=["GET", "POST"])
@admin_required
def new_project():
    project = Project()
    if request.method == "POST":
        error = _read_project(project, request.form, request.files)
        if error:
            flash(error, "error")
            return render_template("admin/project_form.html", project=None,
                                   categories=PROJECT_CATEGORIES,
                                   statuses=PROJECT_STATUSES, form=request.form)
        db.session.add(project)
        db.session.commit()
        flash(f"“{project.title}” is now on the projects page.", "success")
        return redirect(url_for("admin.projects"))
    return render_template("admin/project_form.html", project=None,
                           categories=PROJECT_CATEGORIES,
                           statuses=PROJECT_STATUSES, form=None)


@admin_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_project(project_id):
    project = db.get_or_404(Project, project_id)
    if request.method == "POST":
        error = _read_project(project, request.form, request.files)
        if error:
            flash(error, "error")
            return redirect(url_for("admin.edit_project", project_id=project.id))
        db.session.commit()
        flash("Project updated.", "success")
        return redirect(url_for("admin.projects"))
    return render_template("admin/project_form.html", project=project,
                           categories=PROJECT_CATEGORIES,
                           statuses=PROJECT_STATUSES, form=None)


@admin_bp.post("/projects/<int:project_id>/delete")
@admin_required
def delete_project(project_id):
    project = db.get_or_404(Project, project_id)
    title = project.title
    delete_upload(project.image)
    db.session.delete(project)
    db.session.commit()
    flash(f"“{title}” has been removed.", "success")
    return redirect(url_for("admin.projects"))


@admin_bp.post("/giving")
@admin_required
def update_giving():
    """The account details shown beside the projects."""
    for key, _label in GIVING_FIELDS:
        SiteSetting.put(key, request.form.get(key, "").strip())
    db.session.commit()
    flash("Giving details saved.", "success")
    return redirect(url_for("admin.projects"))


# ---------------------------------------------------------------------------
# Gallery albums
# ---------------------------------------------------------------------------


@admin_bp.route("/gallery")
@admin_required
def albums():
    return render_template(
        "admin/albums.html",
        albums=GalleryAlbum.query.order_by(GalleryAlbum.created_at.desc()).all(),
    )


@admin_bp.route("/gallery/new", methods=["GET", "POST"])
@admin_required
def new_album():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("An album needs a title.", "error")
            return render_template("admin/album_form.html", album=None,
                                   form=request.form, max_photos=MAX_ALBUM_PHOTOS)
        album = GalleryAlbum(
            title=title[:200],
            description=request.form.get("description", "").strip(),
            held_on=request.form.get("held_on", "").strip()[:80],
            location=request.form.get("location", "").strip()[:160],
        )
        db.session.add(album)
        db.session.commit()
        flash("Album created. Now add its photographs.", "success")
        return redirect(url_for("admin.edit_album", album_id=album.id))
    return render_template("admin/album_form.html", album=None, form=None,
                           max_photos=MAX_ALBUM_PHOTOS)


@admin_bp.route("/gallery/<int:album_id>", methods=["GET", "POST"])
@admin_required
def edit_album(album_id):
    """Album details and its photographs, managed on one page."""
    album = db.get_or_404(GalleryAlbum, album_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("An album needs a title.", "error")
            return redirect(url_for("admin.edit_album", album_id=album.id))
        album.title = title[:200]
        album.description = request.form.get("description", "").strip()
        album.held_on = request.form.get("held_on", "").strip()[:80]
        album.location = request.form.get("location", "").strip()[:160]
        db.session.commit()
        flash("Album updated.", "success")
        return redirect(url_for("admin.edit_album", album_id=album.id))
    return render_template("admin/album_form.html", album=album, form=None,
                           max_photos=MAX_ALBUM_PHOTOS)


@admin_bp.post("/gallery/<int:album_id>/photos")
@admin_required
def add_album_photos(album_id):
    """Several photographs at once, which is how an event arrives."""
    album = db.get_or_404(GalleryAlbum, album_id)
    uploads = [f for f in request.files.getlist("photos") if f and f.filename]
    if not uploads:
        flash("Choose at least one photograph to add.", "error")
        return redirect(url_for("admin.edit_album", album_id=album.id))

    room = MAX_ALBUM_PHOTOS - album.count
    if room <= 0:
        flash(f"This album already holds {MAX_ALBUM_PHOTOS} photographs.", "error")
        return redirect(url_for("admin.edit_album", album_id=album.id))

    caption = request.form.get("caption", "").strip()[:400]
    added, refused = 0, []
    for upload in uploads[:room]:
        _, filename, error = save_media(upload, kinds=("image",))
        if error:
            refused.append(f"{upload.filename}: {error}")
            continue
        db.session.add(GalleryPhoto(
            album_id=album.id,
            filename=filename,
            original_name=upload.filename[:255],
            caption=caption,
            # The first photograph in an empty album becomes its cover.
            is_cover=(album.count == 0 and added == 0),
        ))
        added += 1
    db.session.commit()

    if added:
        flash(f"{added} photograph{'s' if added != 1 else ''} added.", "success")
    if len(uploads) > room:
        flash(f"Only {room} more would fit, so {len(uploads) - room} were not added.", "info")
    for message in refused[:4]:
        flash(message, "error")
    return redirect(url_for("admin.edit_album", album_id=album.id))


@admin_bp.post("/gallery/photos/<int:photo_id>/caption")
@admin_required
def caption_photo(photo_id):
    photo = db.get_or_404(GalleryPhoto, photo_id)
    photo.caption = request.form.get("caption", "").strip()[:400]
    db.session.commit()
    flash("Caption saved.", "success")
    return redirect(url_for("admin.edit_album", album_id=photo.album_id))


@admin_bp.post("/gallery/photos/<int:photo_id>/cover")
@admin_required
def make_cover(photo_id):
    """The one photograph that represents this album on the gallery page."""
    photo = db.get_or_404(GalleryPhoto, photo_id)
    for other in photo.album.photos:
        other.is_cover = (other.id == photo.id)
    db.session.commit()
    flash("Cover photograph set.", "success")
    return redirect(url_for("admin.edit_album", album_id=photo.album_id))


@admin_bp.post("/gallery/photos/<int:photo_id>/delete")
@admin_required
def delete_photo(photo_id):
    photo = db.get_or_404(GalleryPhoto, photo_id)
    album_id, was_cover = photo.album_id, photo.is_cover
    delete_upload(photo.filename)
    db.session.delete(photo)
    db.session.commit()

    # Losing the cover would leave the album unrepresented, so promote another.
    album = db.session.get(GalleryAlbum, album_id)
    if was_cover and album and album.photos:
        album.photos[0].is_cover = True
        db.session.commit()
    flash("Photograph removed.", "success")
    return redirect(url_for("admin.edit_album", album_id=album_id))


@admin_bp.post("/gallery/<int:album_id>/delete")
@admin_required
def delete_album(album_id):
    album = db.get_or_404(GalleryAlbum, album_id)
    title = album.title
    for photo in album.photos:
        delete_upload(photo.filename)
    db.session.delete(album)
    db.session.commit()
    flash(f"“{title}” and its photographs have been removed.", "success")
    return redirect(url_for("admin.albums"))


# ---------------------------------------------------------------------------
# Moderating what members post
# ---------------------------------------------------------------------------


@admin_bp.post("/comments/<int:comment_id>/delete")
@admin_required
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted.", "success")
    return redirect(request.referrer or url_for("user.post_detail", post_id=post_id))


@admin_bp.post("/works/<int:work_id>/delete")
@admin_required
def delete_member_work(work_id):
    """Remove a piece of work from a member's portfolio, with its files."""
    work = db.get_or_404(PortfolioWork, work_id)
    user_id, title = work.user_id, work.title
    for item in work.items:
        delete_upload(item.filename)
    db.session.delete(work)
    db.session.commit()
    flash(f"“{title}” has been removed from this member's portfolio.", "success")
    return redirect(url_for("admin.member_detail", user_id=user_id))


@admin_bp.post("/members/<int:user_id>/deactivate")
@admin_required
def deactivate_member(user_id):
    """Suspend an account without destroying anything it holds.

    Everything the member uploaded stays on file, so the decision can be
    reversed; deletion is the separate, irreversible action.
    """
    member = db.get_or_404(User, user_id)
    if member.id == current_user().id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.member_detail", user_id=member.id))
    if member.role == "admin":
        flash("Administrator accounts cannot be deactivated here.", "error")
        return redirect(url_for("admin.member_detail", user_id=member.id))

    member.is_active = False
    member.deactivated_at = datetime.utcnow()
    member.deactivated_reason = request.form.get("reason", "").strip()[:300]
    db.session.commit()
    flash(f"{member.name}'s account is deactivated. They can no longer sign in.", "success")
    return redirect(url_for("admin.member_detail", user_id=member.id))


@admin_bp.post("/members/<int:user_id>/reactivate")
@admin_required
def reactivate_member(user_id):
    member = db.get_or_404(User, user_id)
    member.is_active = True
    member.deactivated_at = None
    member.deactivated_reason = ""
    db.session.commit()
    flash(f"{member.name} can sign in again.", "success")
    return redirect(url_for("admin.member_detail", user_id=member.id))
