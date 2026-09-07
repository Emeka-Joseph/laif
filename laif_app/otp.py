"""One-time passcodes that gate changes to a member's profile.

A pending change is parked on an :class:`OtpChallenge` row together with a
hashed code. Nothing touches the ``User`` record until the member types the
code back, so an abandoned or failed verification leaves the profile as it was.

Delivery is email. When no SMTP host is configured the code goes to the
application log and (in development) onto the verify screen itself, so the
flow stays usable without a mail server. ``send_sms`` is the seam to wire a
gateway such as Twilio in later.
"""

import random
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import current_app

from config import OTP_LENGTH, OTP_MAX_ATTEMPTS, OTP_TTL_MINUTES, RESET_TTL_MINUTES
from laif_app.extensions import db
from laif_app.models import OtpChallenge


def generate_code():
    return f"{random.SystemRandom().randrange(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def create_challenge(user, payload, purpose="profile_update", channel="email", destination=None):
    """Replace any open challenge for this purpose with a fresh one."""
    OtpChallenge.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None).delete()

    # Spent codes are of no further use; drop yesterday's so the table stays small.
    OtpChallenge.query.filter(
        OtpChallenge.user_id == user.id,
        OtpChallenge.consumed_at.isnot(None),
        OtpChallenge.consumed_at < datetime.utcnow() - timedelta(days=1),
    ).delete(synchronize_session=False)

    code = generate_code()
    challenge = OtpChallenge(
        user_id=user.id,
        purpose=purpose,
        channel=channel,
        destination=destination or user.email,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    challenge.set_code(code)
    challenge.payload = payload
    db.session.add(challenge)
    db.session.commit()
    return challenge, code


def open_challenge(user, purpose="profile_update"):
    """The member's current unconsumed challenge, if one is still live."""
    challenge = (
        OtpChallenge.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None)
        .order_by(OtpChallenge.id.desc())
        .first()
    )
    return challenge if challenge and not challenge.expired else None


def verify(challenge, code):
    """Check a submitted code. Returns (ok, message)."""
    if challenge.expired:
        return False, "That passcode has expired. Please request a new one."
    if challenge.attempts >= OTP_MAX_ATTEMPTS:
        return False, "Too many incorrect attempts. Please request a new passcode."

    if not challenge.check_code((code or "").strip()):
        challenge.attempts += 1
        db.session.commit()
        remaining = OTP_MAX_ATTEMPTS - challenge.attempts
        if remaining <= 0:
            return False, "Too many incorrect attempts. Please request a new passcode."
        return False, f"That passcode is not correct. {remaining} attempt(s) left."

    challenge.consumed_at = datetime.utcnow()
    db.session.commit()
    return True, "Verified."


def send_code(user, code, challenge):
    """Deliver the passcode. Returns True when a real message went out."""
    current_app.logger.info("OTP for %s (%s): %s", user.email, challenge.purpose, code)

    if challenge.channel == "sms":
        return send_sms(challenge.destination, code)
    return send_email(challenge.destination, user, code)


def _tls_context():
    """A verifying context, unless the host's mail server is self-signed."""
    context = ssl.create_default_context()
    if not current_app.config.get("SMTP_VERIFY_CERT", True):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def send_mail(address, subject, body):
    """Deliver one plain-text message. Returns True when it went out.

    Two dialects are in play: port 465 is wrapped in TLS from the first byte,
    while 587 opens in the clear and upgrades with STARTTLS. ``SMTP_USE_SSL``
    chooses between them and takes its default from the port number.
    """
    host = current_app.config.get("SMTP_HOST")
    if not host:
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config["MAIL_SENDER"]
    message["To"] = address
    message.set_content(body)

    port = current_app.config["SMTP_PORT"]
    use_ssl = current_app.config.get("SMTP_USE_SSL", False)

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=_tls_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            if not use_ssl and current_app.config["SMTP_USE_TLS"]:
                server.starttls(context=_tls_context())
                server.ehlo()
            if current_app.config["SMTP_USER"]:
                server.login(current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"])
            server.send_message(message)
        return True
    except Exception as exc:  # noqa: BLE001 — never break the flow on mail trouble
        current_app.logger.warning(
            "Could not send mail to %s via %s:%s (ssl=%s): %s", address, host, port, use_ssl, exc
        )
        return False


def send_email(address, user, code):
    """The passcode message itself."""
    return send_mail(
        address,
        "Your LAIF Community passcode",
        f"Hello {user.name},\n\n"
        f"Your one-time passcode is {code}.\n"
        f"It expires in {OTP_TTL_MINUTES} minutes.\n\n"
        "If you did not request a profile change you can ignore this message "
        "and your details will stay exactly as they are.\n\n"
        "— LAIF Community",
    )


def send_reset_link(user, url):
    """Mail a password-reset link. Returns True when it went out."""
    return send_mail(
        user.email,
        "Reset your LAIF Community password",
        f"Hello {user.name},\n\n"
        "Someone asked to reset the password on your LAIF Community account. "
        "Open the link below to choose a new one:\n\n"
        f"{url}\n\n"
        f"The link stops working in {RESET_TTL_MINUTES} minutes. If this was not "
        "you, ignore this message — your password stays as it is.\n\n"
        "— LAIF Community",
    )


def send_sms(number, code):
    """Placeholder for an SMS gateway; logs and reports no delivery."""
    current_app.logger.info("SMS gateway not configured — passcode for %s not sent.", number)
    return False


def mask_destination(challenge):
    """A privacy-friendly hint of where the code went, e.g. jo••@mail.com."""
    value = challenge.destination or ""
    if challenge.channel == "sms":
        return "•" * max(0, len(value) - 3) + value[-3:] if len(value) > 3 else value
    name, _, domain = value.partition("@")
    if not domain:
        return value
    head = name[:2] if len(name) > 2 else name[:1]
    return f"{head}{'•' * max(2, len(name) - len(head))}@{domain}"
