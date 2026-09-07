import json
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from laif_app.extensions import db


class AccessCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="member")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="member")
    bio = db.Column(db.Text, default="")
    skills = db.Column(db.String(255), default="")
    photo = db.Column(db.String(255), default="")
    phone = db.Column(db.String(40), default="")
    address = db.Column(db.String(255), default="")
    city = db.Column(db.String(120), default="")
    country = db.Column(db.String(120), default="")
    reset_token = db.Column(db.String(64), unique=True, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def skill_list(self):
        return [s.strip() for s in (self.skills or "").split(",") if s.strip()]

    @property
    def location(self):
        return ", ".join(part for part in (self.city, self.country) if part)

    @property
    def initials(self):
        parts = [p for p in (self.name or "").split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(220), nullable=False)
    excerpt = db.Column(db.String(400), default="")
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255), default="")
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    likes = db.Column(db.Integer, default=0)
    author = db.relationship("User", backref="posts")


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(700), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    post = db.relationship("Post", backref=db.backref("comments", lazy=True, cascade="all, delete-orphan"))


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(400), default="")
    filename = db.Column(db.String(255), nullable=True)
    original_name = db.Column(db.String(255), nullable=True)
    link = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(60), default="")
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PortfolioWork(db.Model):
    """One job a member has previously done.

    A work holds its own gallery of photos and clips plus any links out to a
    website or social media handle, so a visitor can open a single job and see
    everything about it in one place.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(400), default="")
    description = db.Column(db.Text, default="")
    client = db.Column(db.String(160), default="")
    done_on = db.Column(db.String(80), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship(
        "User",
        backref=db.backref(
            "works",
            lazy=True,
            order_by="PortfolioWork.created_at.desc()",
            cascade="all, delete-orphan",
        ),
    )

    @property
    def cover(self):
        """The tile shown in the grid: the first photo, else the first clip."""
        for item in self.items:
            if not item.is_video:
                return item
        return self.items[0] if self.items else None

    @property
    def meta_line(self):
        return " · ".join(part for part in (self.client, self.done_on) if part)


class PortfolioItem(db.Model):
    """A photo or short clip belonging to one previous job."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    work_id = db.Column(db.Integer, db.ForeignKey("portfolio_work.id"), nullable=True)
    kind = db.Column(db.String(10), nullable=False, default="image")  # image | video
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), default="")
    title = db.Column(db.String(160), default="")
    description = db.Column(db.String(400), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship(
        "User",
        backref=db.backref("portfolio", lazy=True, order_by="PortfolioItem.created_at.desc()", cascade="all, delete-orphan"),
    )
    work = db.relationship(
        "PortfolioWork",
        backref=db.backref("items", lazy=True, order_by="PortfolioItem.id", cascade="all, delete-orphan"),
    )

    @property
    def is_video(self):
        return self.kind == "video"


class LinkMixin:
    """Shared reading of a stored website or social media address."""

    @property
    def host(self):
        """The bare domain, used as a fallback label and in the link chip."""
        rest = self.url.split("://", 1)[-1]
        return rest.split("/", 1)[0].removeprefix("www.")

    @property
    def display(self):
        return self.label or self.host


class WorkLink(LinkMixin, db.Model):
    """A website or social media handle attached to a previous job."""

    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("portfolio_work.id"), nullable=False)
    label = db.Column(db.String(80), default="")
    url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    work = db.relationship(
        "PortfolioWork",
        backref=db.backref("links", lazy=True, order_by="WorkLink.id", cascade="all, delete-orphan"),
    )


class MemberLink(LinkMixin, db.Model):
    """A member's own website or social media handle, shown on their profile.

    Separate from WorkLink: these describe the person rather than any one job,
    so they stay on the profile even as pieces of work come and go.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    label = db.Column(db.String(80), default="")
    url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship(
        "User",
        backref=db.backref("links", lazy=True, order_by="MemberLink.id", cascade="all, delete-orphan"),
    )


class OtpChallenge(db.Model):
    """A pending profile change held back until its passcode is confirmed."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    purpose = db.Column(db.String(40), nullable=False, default="profile_update")
    code_hash = db.Column(db.String(255), nullable=False)
    channel = db.Column(db.String(20), nullable=False, default="email")
    destination = db.Column(db.String(160), nullable=False, default="")
    payload_json = db.Column(db.Text, default="{}")
    attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship("User", backref=db.backref("otp_challenges", lazy=True, cascade="all, delete-orphan"))

    @property
    def payload(self):
        try:
            return json.loads(self.payload_json or "{}")
        except ValueError:
            return {}

    @payload.setter
    def payload(self, value):
        self.payload_json = json.dumps(value)

    @property
    def expired(self):
        return datetime.utcnow() >= self.expires_at

    @property
    def seconds_left(self):
        return max(0, int((self.expires_at - datetime.utcnow()).total_seconds()))

    def set_code(self, code):
        self.code_hash = generate_password_hash(code)

    def check_code(self, code):
        return check_password_hash(self.code_hash, code)
