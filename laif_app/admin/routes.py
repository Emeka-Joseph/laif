import os
import secrets

from flask import flash, redirect, render_template, request, session, url_for

from config import RESOURCE_CATEGORIES, UPLOAD_DIR
from laif_app.admin import admin_bp
from laif_app.extensions import db
from laif_app.helpers import admin_required, allowed_resource_file, current_user, delete_upload
from laif_app.models import AccessCode, ContactMessage, Post, Resource, User


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    user = current_user()
    if user and user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        candidate = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        if candidate and candidate.role == "admin" and candidate.check_password(request.form.get("password", "")):
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
        stats={
            "members": User.query.filter_by(role="member").count(),
            "posts": Post.query.count(),
            "resources": Resource.query.count(),
            "codes": AccessCode.query.filter_by(kind="member").count(),
            "messages": ContactMessage.query.count(),
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

    query = User.query
    if role in {"member", "admin"}:
        query = query.filter_by(role=role)
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
        return f"This account wrote {count} blog post{'s' if count != 1 else ''}. Delete or reassign them first."
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
