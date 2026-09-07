from flask import current_app
from sqlalchemy import inspect, text

from config import DEFAULT_ADMIN_PASSWORD
from laif_app.extensions import db
from laif_app.models import PortfolioItem, PortfolioWork, Post, Resource, User


def sync_columns():
    """Add columns that models declare but an existing table is missing.

    The project has no migration tool, so `db.create_all()` alone would leave
    older databases without the newer profile fields. Only additive changes are
    made here — nothing is dropped or retyped.
    """
    inspector = inspect(db.engine)
    dialect = db.engine.dialect

    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            column_type = column.type.compile(dialect)
            default = ""
            if column.default is not None and not callable(getattr(column.default, "arg", None)):
                default = f" DEFAULT {column.default.arg!r}"
            statement = (
                f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type} NULL{default}"
            )
            db.session.execute(text(statement))
            db.session.commit()


def backfill_works():
    """Give every loose portfolio photo a previous-work entry of its own.

    Before jobs existed each upload stood alone with its own caption. Wrapping
    each one in a work of the same name keeps those captions intact and lets
    the member merge or extend them from the dashboard afterwards.
    """
    loose = PortfolioItem.query.filter(PortfolioItem.work_id.is_(None)).order_by(PortfolioItem.id).all()
    for item in loose:
        work = PortfolioWork(
            user_id=item.user_id,
            title=(item.title or item.original_name or "Previous work")[:200],
            summary=(item.description or "")[:400],
            description=item.description or "",
            created_at=item.created_at,
        )
        db.session.add(work)
        db.session.flush()
        item.work_id = work.id
    if loose:
        db.session.commit()


def seed():
    db.create_all()
    sync_columns()
    backfill_works()
    if not User.query.filter_by(role="admin").first():
        admin_user = User(
            name="LAIF Administrator",
            email=current_app.config["ADMIN_EMAIL"],
            role="admin",
        )
        admin_user.set_password(current_app.config["ADMIN_PASSWORD"])
        db.session.add(admin_user)
        if current_app.config["ADMIN_PASSWORD"] == DEFAULT_ADMIN_PASSWORD:
            current_app.logger.warning(
                "Seeded the administrator with the published default password. "
                "Set LAIF_ADMIN_PASSWORD and change it before this site is public."
            )
    if not Resource.query.first():
        db.session.add_all([
            Resource(title="Rooted in Grace", category="E-books", description="A 21-day devotional for growing deeper in God."),
            Resource(title="The Family Table", category="Family & life", description="Practical prompts for faith-filled homes."),
            Resource(title="Foundations of Faith", category="Study guides", description="A small-group guide for new and growing believers."),
        ])
    if not Post.query.first():
        db.session.commit()
        admin_user = User.query.filter_by(role="admin").first()
        db.session.add(Post(
            title="There is more grace for today",
            excerpt="A fresh word for the week ahead.",
            content="Every new morning is a reminder that God is still writing your story. Walk in courage, serve with joy, and make room for the people around you to encounter hope.",
            image="4C4A3910.JPG",
            author_id=admin_user.id,
        ))
    db.session.commit()
