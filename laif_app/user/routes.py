import secrets
from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, send_from_directory, session, url_for

from config import (
    IMAGES_DIR,
    MAX_MEMBER_LINKS,
    MAX_PORTFOLIO_ITEMS,
    MAX_PORTFOLIO_WORKS,
    MAX_WORK_LINKS,
    MAX_WORK_MEDIA,
    OTP_LENGTH,
    OTP_RESEND_SECONDS,
    RESOURCE_CATEGORIES,
    UPLOAD_DIR,
)
from laif_app import otp
from laif_app.extensions import db
from laif_app.helpers import current_user, delete_upload, login_required, normalize_link, save_media
from laif_app.models import (
    AccessCode,
    Comment,
    ContactMessage,
    MemberLink,
    OtpChallenge,
    PortfolioItem,
    PortfolioWork,
    Post,
    Resource,
    User,
    WorkLink,
)
from laif_app.user import user_bp


# Wide shots only: these files carry no EXIF rotation, so they crop predictably
# in the landscape gallery frame.
GALLERY = [
    {"file": "4C4A3603.JPG", "caption": "Gathered in worship"},
    {"file": "4C4A3166.JPG", "caption": "Our children's church"},
    {"file": "4C4A3594.JPG", "caption": "Celebrating together"},
    {"file": "4C4A3473.JPG", "caption": "The 15th Annual Convention"},
    {"file": "4C4A3222.JPG", "caption": "Fellowship after service"},
    {"file": "4C4A3778.JPG", "caption": "One family, many nations"},
]


@user_bp.route("/")
def home():
    return render_template("user/home.html", gallery=GALLERY)


@user_bp.route("/images/<path:filename>")
def church_image(filename):
    return send_from_directory(IMAGES_DIR, filename)


@user_bp.route("/about")
def about():
    return render_template("user/about.html")


@user_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        message = request.form.get("message", "").strip()
        if name and email and message:
            db.session.add(ContactMessage(name=name, email=email, phone=phone, message=message))
            db.session.commit()
            flash("Thank you for reaching out. Our team will get back to you soon.", "success")
            return redirect(url_for("user.contact"))
        flash("Please fill in your name, email and message.", "error")
    return render_template("user/contact.html")


@user_bp.route("/live")
def live():
    return render_template("user/live.html")


@user_bp.route("/resources")
def resources():
    categories = ["All"] + RESOURCE_CATEGORIES
    selected = request.args.get("category", "All")
    query = Resource.query if selected == "All" else Resource.query.filter_by(category=selected)
    return render_template(
        "user/resources.html",
        resources=query.order_by(Resource.id.desc()).all(),
        categories=categories,
        selected=selected,
    )


@user_bp.route("/resources/download/<int:resource_id>")
def download_resource(resource_id):
    resource = db.get_or_404(Resource, resource_id)
    if resource.filename:
        return send_from_directory(UPLOAD_DIR, resource.filename, as_attachment=True, download_name=resource.original_name or resource.filename)
    if resource.link:
        return redirect(resource.link)
    flash("This resource is not available yet.", "info")
    return redirect(url_for("user.resources"))


@user_bp.route("/skills")
def skills():
    members = (
        User.query.filter_by(role="member")
        .filter(db.or_(User.skills != "", User.bio != ""))
        .order_by(User.name)
        .all()
    )
    return render_template("user/skills.html", members=members)


@user_bp.route("/members/<int:user_id>")
def member_profile(user_id):
    member = db.get_or_404(User, user_id)
    if member.role == "admin":
        flash("That profile is not part of the member directory.", "info")
        return redirect(url_for("user.skills"))
    return render_template("user/member.html", member=member, works=member.works)


@user_bp.route("/members/<int:user_id>/work/<int:work_id>")
def member_work(user_id, work_id):
    """One previous job, opened from a tile on the member's profile."""
    member = db.get_or_404(User, user_id)
    work = db.get_or_404(PortfolioWork, work_id)
    if work.user_id != member.id:
        flash("That piece of work is not on this profile.", "info")
        return redirect(url_for("user.member_profile", user_id=member.id))

    siblings = member.works
    position = siblings.index(work) if work in siblings else 0
    return render_template(
        "user/work.html",
        member=member,
        work=work,
        items=work.items,
        links=work.links,
        previous=siblings[position - 1] if position > 0 else None,
        following=siblings[position + 1] if position + 1 < len(siblings) else None,
    )


@user_bp.route("/blog")
def blog():
    return render_template("user/blog.html", posts=Post.query.order_by(Post.created_at.desc()).all())


@user_bp.route("/blog/<int:post_id>", methods=["GET", "POST"])
def post_detail(post_id):
    post = db.get_or_404(Post, post_id)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        name = current_user().name if current_user() else request.form.get("name", "A friend").strip()
        if body and name:
            db.session.add(Comment(body=body, name=name, post=post))
            db.session.commit()
            flash("Your comment has been added.", "success")
        else:
            flash("Please add a name and comment.", "error")
        return redirect(url_for("user.post_detail", post_id=post_id))
    share_url = url_for("user.post_detail", post_id=post_id, _external=True)
    return render_template("user/post_detail.html", post=post, share_url=share_url)


@user_bp.post("/blog/<int:post_id>/like")
def like_post(post_id):
    post = db.get_or_404(Post, post_id)
    post.likes += 1
    db.session.commit()
    return redirect(request.referrer or url_for("user.blog"))


@user_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        if user and user.check_password(request.form.get("password", "")):
            session["user_id"] = user.id
            landing = url_for("admin.dashboard") if user.role == "admin" else url_for("user.dashboard")
            return redirect(request.args.get("next") or landing)
        flash("Email or password not recognised.", "error")
    return render_template("user/auth.html", mode="login")


@user_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        if user:
            user.reset_token = secrets.token_urlsafe(32)
            db.session.commit()
            flash("Your reset link is ready below.", "success")
            return render_template("user/forgot.html", reset_url=url_for("user.reset_password", token=user.reset_token, _external=True))
        flash("If that email is registered, a reset link will be available shortly.", "info")
    return render_template("user/forgot.html")


@user_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first_or_404()
    if request.method == "POST":
        user.set_password(request.form.get("password", ""))
        user.reset_token = None
        db.session.commit()
        flash("Your password has been updated. Please sign in.", "success")
        return redirect(url_for("user.login"))
    return render_template("user/reset.html")


@user_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        code = AccessCode.query.filter_by(code=request.form.get("code", "").strip().upper(), kind="member").first()
        email = request.form.get("email", "").lower().strip()
        if not code:
            flash("That member invitation code is invalid or already used.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(name=request.form.get("name", "").strip(), email=email, skills=request.form.get("skills", "").strip(), bio=request.form.get("bio", "").strip())
            user.set_password(request.form.get("password", ""))
            db.session.add(user)
            db.session.delete(code)
            db.session.commit()
            flash("Welcome to the LAIF talent community. You can now sign in.", "success")
            return redirect(url_for("user.login"))
    return render_template("user/auth.html", mode="signup")


@user_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("user.home"))


# ---------------------------------------------------------------------------
# Member dashboard
# ---------------------------------------------------------------------------

# Editable profile fields, in the order they appear on the form.
PROFILE_FIELDS = ("name", "email", "phone", "address", "city", "country", "skills", "bio")


def _discard_pending(user):
    """Drop unfinished profile changes and any photos they were holding.

    Expired challenges are swept up too, so an abandoned picture upload does
    not sit in the uploads folder unreferenced.
    """
    stale = OtpChallenge.query.filter_by(user_id=user.id, purpose="profile_update", consumed_at=None).all()
    for challenge in stale:
        delete_upload(challenge.payload.get("photo"))
        db.session.delete(challenge)
    db.session.commit()


def _deliver(user, challenge, code):
    """Send the passcode and stash it for on-screen display in development."""
    delivered = otp.send_code(user, code, challenge)
    session.pop("otp_preview", None)
    if not delivered and current_app.config.get("OTP_SHOW_IN_UI"):
        session["otp_preview"] = code
    return delivered


@user_bp.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    return render_template(
        "user/dashboard.html",
        user=user,
        works=user.works,
        pending=otp.open_challenge(user),
        media_used=len(user.portfolio),
        max_items=MAX_PORTFOLIO_ITEMS,
        max_works=MAX_PORTFOLIO_WORKS,
        max_links=MAX_WORK_LINKS,
        member_links=user.links,
        max_member_links=MAX_MEMBER_LINKS,
    )


@user_bp.post("/dashboard/profile")
@login_required
def update_profile():
    user = current_user()
    submitted = {field: request.form.get(field, "").strip() for field in PROFILE_FIELDS}
    submitted["email"] = submitted["email"].lower()

    if not submitted["name"]:
        flash("Your name cannot be empty.", "error")
        return redirect(url_for("user.dashboard"))
    if not submitted["email"]:
        flash("Your email address cannot be empty.", "error")
        return redirect(url_for("user.dashboard"))
    if submitted["email"] != user.email and User.query.filter_by(email=submitted["email"]).first():
        flash("Another account already uses that email address.", "error")
        return redirect(url_for("user.dashboard"))

    changes = {f: v for f, v in submitted.items() if v != (getattr(user, f) or "")}

    # A replacement photo is stored straight away under a random name; the
    # profile only starts pointing at it once the passcode checks out.
    remove_photo = request.form.get("remove_photo") == "1"
    photo_name = None
    upload = request.files.get("photo")
    if upload and upload.filename:
        _, photo_name, error = save_media(upload, kinds=("image",))
        if error:
            flash(error, "error")
            return redirect(url_for("user.dashboard"))
        remove_photo = False

    if not changes and not photo_name and not remove_photo:
        flash("Nothing to update - your details are unchanged.", "info")
        return redirect(url_for("user.dashboard"))

    _discard_pending(user)
    payload = {"fields": changes, "photo": photo_name, "remove_photo": remove_photo}
    challenge, code = otp.create_challenge(user, payload, destination=user.email)
    _deliver(user, challenge, code)

    flash("For your security we sent a passcode. Enter it to save these changes.", "info")
    return redirect(url_for("user.verify_profile"))


@user_bp.route("/dashboard/verify", methods=["GET", "POST"])
@login_required
def verify_profile():
    user = current_user()
    challenge = otp.open_challenge(user)
    if not challenge:
        flash("There is no profile change waiting for a passcode.", "info")
        return redirect(url_for("user.dashboard"))

    if request.method == "POST":
        ok, message = otp.verify(challenge, request.form.get("code", ""))
        if not ok:
            flash(message, "error")
            return redirect(url_for("user.verify_profile"))

        payload = challenge.payload
        for field, value in payload.get("fields", {}).items():
            setattr(user, field, value)
        if payload.get("photo"):
            delete_upload(user.photo)
            user.photo = payload["photo"]
        elif payload.get("remove_photo"):
            delete_upload(user.photo)
            user.photo = ""
        db.session.commit()
        session.pop("otp_preview", None)

        flash("Verified - your profile has been updated.", "success")
        return redirect(url_for("user.dashboard"))

    return render_template(
        "user/verify.html",
        challenge=challenge,
        masked=otp.mask_destination(challenge),
        code_length=OTP_LENGTH,
        preview=session.get("otp_preview"),
        changes=challenge.payload.get("fields", {}),
        photo_pending=bool(challenge.payload.get("photo")),
        photo_removed=bool(challenge.payload.get("remove_photo")),
    )


@user_bp.post("/dashboard/verify/resend")
@login_required
def resend_passcode():
    user = current_user()
    challenge = otp.open_challenge(user)
    if not challenge:
        flash("There is no profile change waiting for a passcode.", "info")
        return redirect(url_for("user.dashboard"))

    age = (datetime.utcnow() - challenge.created_at).total_seconds()
    if age < OTP_RESEND_SECONDS:
        wait = int(OTP_RESEND_SECONDS - age)
        flash(f"Please wait {wait} more seconds before asking for another passcode.", "info")
        return redirect(url_for("user.verify_profile"))

    fresh, code = otp.create_challenge(user, challenge.payload, destination=challenge.destination)
    _deliver(user, fresh, code)
    flash("A new passcode is on its way.", "success")
    return redirect(url_for("user.verify_profile"))


@user_bp.post("/dashboard/verify/cancel")
@login_required
def cancel_profile_change():
    _discard_pending(current_user())
    session.pop("otp_preview", None)
    flash("Those changes were discarded. Your profile is unchanged.", "info")
    return redirect(url_for("user.dashboard"))


# ---------------------------------------------------------------------------
# Profile links - the member's own website and social media handles
# ---------------------------------------------------------------------------
#
# These sit outside the passcode flow that guards the profile fields. They are
# public showcase links rather than contact details the account is recovered
# with, and asking for a passcode per handle would make listing four of them a
# chore. Removing one is a single click, so a mistake is cheap to undo.


@user_bp.post("/dashboard/profile/links")
@login_required
def add_member_link():
    """Add a website or social media handle to the member's own profile."""
    user = current_user()
    pairs, problems = _read_links(request.form, len(user.links), MAX_MEMBER_LINKS, "Your profile")
    for label, url in pairs:
        db.session.add(MemberLink(user_id=user.id, label=label, url=url))
    db.session.commit()

    for problem in problems:
        flash(problem, "error")
    if pairs:
        flash(f"{len(pairs)} link{'s' if len(pairs) != 1 else ''} added to your profile.", "success")
    elif not problems:
        flash("Please paste a website address or social media link.", "error")
    return redirect(url_for("user.dashboard"))


@user_bp.post("/dashboard/profile/links/<int:link_id>/delete")
@login_required
def delete_member_link(link_id):
    link = db.get_or_404(MemberLink, link_id)
    if link.user_id != current_user().id:
        flash("That link is not yours to remove.", "error")
        return redirect(url_for("user.dashboard"))

    db.session.delete(link)
    db.session.commit()
    flash("Link removed from your profile.", "success")
    return redirect(url_for("user.dashboard"))


# ---------------------------------------------------------------------------
# Previous work - a job, its gallery of photos and clips, and its links
# ---------------------------------------------------------------------------


def _own_work(work_id):
    """Fetch a previous-work entry, or None when it belongs to someone else."""
    work = db.get_or_404(PortfolioWork, work_id)
    return work if work.user_id == current_user().id else None


def _attach_media(work, uploads):
    """Store the chosen photos and clips against a job.

    Returns (added, problems) so the caller can report partial success: one
    oversized file in a multi-file pick should not throw away the rest.
    """
    user = work.user
    # Counted once up front: adding to the session can flush, after which the
    # relationships would already include what this loop has just stored.
    in_work, in_portfolio = len(work.items), len(user.portfolio)

    added, problems = 0, []
    for upload in uploads:
        if not upload or not upload.filename:
            continue
        if in_work + added >= MAX_WORK_MEDIA:
            problems.append(f"Only {MAX_WORK_MEDIA} files fit in one piece of work, so the rest were skipped.")
            break
        if in_portfolio + added >= MAX_PORTFOLIO_ITEMS:
            problems.append(f"Your portfolio is full ({MAX_PORTFOLIO_ITEMS} files across all your work).")
            break

        kind, filename, error = save_media(upload)
        if error:
            problems.append(f"{upload.filename}: {error}")
            continue

        db.session.add(PortfolioItem(
            user_id=user.id,
            work_id=work.id,
            kind=kind,
            filename=filename,
            original_name=upload.filename[:255],
        ))
        added += 1
    return added, problems


def _read_links(form, existing, limit, subject):
    """Validate the label/address rows submitted with a form.

    Every link form on the site — the one inside "add new work", the job's own
    page, and the member's profile — sends the same repeating pair of fields,
    so one reader serves them all. Returns (pairs, problems); blank rows are
    skipped and a bad address is reported without discarding the good ones.
    """
    room = limit - existing
    pairs, problems = [], []
    for label, raw in zip(form.getlist("link_label"), form.getlist("link_url")):
        if not raw.strip():
            continue
        if len(pairs) >= room:
            problems.append(f"{subject} can carry up to {limit} links, so the rest were skipped.")
            break

        url, error = normalize_link(raw)
        if error:
            problems.append(f"{raw.strip()[:60]} - {error}")
            continue

        pairs.append((label.strip()[:80], url))
    return pairs, problems


def _attach_links(work, form):
    """Store the websites and social media handles submitted against a job."""
    pairs, problems = _read_links(form, len(work.links), MAX_WORK_LINKS, "A piece of work")
    for label, url in pairs:
        db.session.add(WorkLink(work_id=work.id, label=label, url=url))
    return len(pairs), problems


@user_bp.post("/dashboard/works")
@login_required
def add_work():
    """Start a new previous-work entry, optionally with its first pictures."""
    user = current_user()
    if len(user.works) >= MAX_PORTFOLIO_WORKS:
        flash(f"You already have {MAX_PORTFOLIO_WORKS} pieces of work listed. Remove one to add another.", "error")
        return redirect(url_for("user.dashboard"))

    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("Please give this piece of work a title.", "error")
        return redirect(url_for("user.dashboard"))

    work = PortfolioWork(
        user_id=user.id,
        title=title,
        summary=request.form.get("summary", "").strip()[:400],
        description=request.form.get("description", "").strip(),
        client=request.form.get("client", "").strip()[:160],
        done_on=request.form.get("done_on", "").strip()[:80],
    )
    db.session.add(work)
    db.session.flush()

    _, problems = _attach_media(work, request.files.getlist("media"))
    _, link_problems = _attach_links(work, request.form)
    db.session.commit()
    for problem in problems + link_problems:
        flash(problem, "error")

    flash(f"“{work.title}” was added to your previous work. Add more pictures and links below.", "success")
    return redirect(url_for("user.edit_work", work_id=work.id))


@user_bp.route("/dashboard/works/<int:work_id>")
@login_required
def edit_work(work_id):
    """The member's own view of one job: its pictures, wording and links."""
    work = _own_work(work_id)
    if not work:
        flash("That piece of work is not yours to edit.", "error")
        return redirect(url_for("user.dashboard"))

    return render_template(
        "user/work_edit.html",
        user=current_user(),
        work=work,
        items=work.items,
        links=work.links,
        max_media=MAX_WORK_MEDIA,
        max_links=MAX_WORK_LINKS,
    )


@user_bp.post("/dashboard/works/<int:work_id>/edit")
@login_required
def update_work(work_id):
    work = _own_work(work_id)
    if not work:
        flash("That piece of work is not yours to edit.", "error")
        return redirect(url_for("user.dashboard"))

    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("A piece of work needs a title.", "error")
        return redirect(url_for("user.edit_work", work_id=work.id))

    work.title = title
    work.summary = request.form.get("summary", "").strip()[:400]
    work.description = request.form.get("description", "").strip()
    work.client = request.form.get("client", "").strip()[:160]
    work.done_on = request.form.get("done_on", "").strip()[:80]
    db.session.commit()
    flash("Saved.", "success")
    return redirect(url_for("user.edit_work", work_id=work.id))


@user_bp.post("/dashboard/works/<int:work_id>/delete")
@login_required
def delete_work(work_id):
    work = _own_work(work_id)
    if not work:
        flash("That piece of work is not yours to remove.", "error")
        return redirect(url_for("user.dashboard"))

    for item in work.items:
        delete_upload(item.filename)
    db.session.delete(work)
    db.session.commit()
    flash("That piece of work and its pictures were removed.", "success")
    return redirect(url_for("user.dashboard"))


@user_bp.post("/dashboard/works/<int:work_id>/media")
@login_required
def add_work_media(work_id):
    """Add another image or clip to a job already on the profile."""
    work = _own_work(work_id)
    if not work:
        flash("That piece of work is not yours to edit.", "error")
        return redirect(url_for("user.dashboard"))

    added, problems = _attach_media(work, request.files.getlist("media"))
    db.session.commit()
    for problem in problems:
        flash(problem, "error")
    if added:
        flash(f"{added} file{'s' if added != 1 else ''} added to this piece of work.", "success")
    elif not problems:
        flash("Please choose a photo or clip to add.", "error")
    return redirect(url_for("user.edit_work", work_id=work.id))


def _own_item(item_id):
    """Fetch a portfolio image, or None when it belongs to someone else."""
    item = db.get_or_404(PortfolioItem, item_id)
    return item if item.user_id == current_user().id else None


def _back_to_work(item):
    """Where a media edit returns to: its job, or the dashboard if loose."""
    if item.work_id:
        return redirect(url_for("user.edit_work", work_id=item.work_id))
    return redirect(url_for("user.dashboard"))


@user_bp.post("/dashboard/media/<int:item_id>/edit")
@login_required
def edit_portfolio_item(item_id):
    item = _own_item(item_id)
    if not item:
        flash("That picture is not yours to edit.", "error")
        return redirect(url_for("user.dashboard"))

    item.title = request.form.get("title", "").strip()[:160]
    item.description = request.form.get("description", "").strip()[:400]
    db.session.commit()
    flash("Caption updated.", "success")
    return _back_to_work(item)


@user_bp.post("/dashboard/media/<int:item_id>/delete")
@login_required
def delete_portfolio_item(item_id):
    item = _own_item(item_id)
    if not item:
        flash("That picture is not yours to remove.", "error")
        return redirect(url_for("user.dashboard"))

    destination = _back_to_work(item)
    delete_upload(item.filename)
    db.session.delete(item)
    db.session.commit()
    flash("Picture removed.", "success")
    return destination


@user_bp.post("/dashboard/works/<int:work_id>/links")
@login_required
def add_work_link(work_id):
    """Attach a website or social media handle for visitors to follow."""
    work = _own_work(work_id)
    if not work:
        flash("That piece of work is not yours to edit.", "error")
        return redirect(url_for("user.dashboard"))

    added, problems = _attach_links(work, request.form)
    db.session.commit()
    for problem in problems:
        flash(problem, "error")
    if added:
        flash(f"{added} link{'s' if added != 1 else ''} added.", "success")
    elif not problems:
        flash("Please paste a website address or social media link.", "error")
    return redirect(url_for("user.edit_work", work_id=work.id))


@user_bp.post("/dashboard/links/<int:link_id>/delete")
@login_required
def delete_work_link(link_id):
    link = db.get_or_404(WorkLink, link_id)
    if link.work.user_id != current_user().id:
        flash("That link is not yours to remove.", "error")
        return redirect(url_for("user.dashboard"))

    work_id = link.work_id
    db.session.delete(link)
    db.session.commit()
    flash("Link removed.", "success")
    return redirect(url_for("user.edit_work", work_id=work_id))
