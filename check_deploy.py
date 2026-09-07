"""Pre-flight check for a LAIF deployment.

Run it on the server, inside the application's virtualenv, before announcing
the site:

    python check_deploy.py                     # settings, database, mail login
    python check_deploy.py you@example.com     # ... and send a real test email

It reads the same configuration the site does, so a PASS here means the running
app sees the same thing.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_ADMIN_PASSWORD, DEV_SECRET_KEY, Config  # noqa: E402

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = RED = YELLOW = RESET = ""

results = []


def record(level, label, detail=""):
    results.append((level, label))
    colour = {"PASS": GREEN, "FAIL": RED, "WARN": YELLOW}[level]
    print(f"  {colour}{level:4}{RESET}  {label}")
    if detail:
        for line in str(detail).splitlines():
            print(f"          {line}")


def mask(value):
    if not value:
        return "(unset)"
    return value[0] + "*" * (len(value) - 2) + value[-1] if len(value) > 2 else "**"


def check_settings():
    print("\nSettings")
    if Config.SECRET_KEY == DEV_SECRET_KEY:
        record("FAIL", "LAIF_SECRET_KEY is unset",
               "Sessions are signed with the key published in the repository, so "
               "anyone can forge a login cookie. Set it to a long random string.")
    else:
        record("PASS", f"LAIF_SECRET_KEY is set ({len(Config.SECRET_KEY)} characters)")

    if Config.ADMIN_PASSWORD == DEFAULT_ADMIN_PASSWORD:
        record("FAIL", "LAIF_ADMIN_PASSWORD is unset",
               "The administrator account would be created with the default "
               "password published in the repository.")
    else:
        record("PASS", f"LAIF_ADMIN_PASSWORD is set for {Config.ADMIN_EMAIL}")

    if Config.OTP_SHOW_IN_UI:
        record("FAIL", "LAIF_OTP_SHOW_IN_UI is on",
               "Passcodes and password-reset links would be shown in the browser "
               "whenever mail delivery fails. Set LAIF_OTP_SHOW_IN_UI=0.")
    else:
        record("PASS", "LAIF_OTP_SHOW_IN_UI is off")

    if not os.access(Config.UPLOAD_FOLDER, os.W_OK):
        record("FAIL", "uploads folder is not writable", Config.UPLOAD_FOLDER)
    else:
        record("PASS", "uploads folder is writable")


def check_database():
    print("\nDatabase")
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        safe = Config.SQLALCHEMY_DATABASE_URI.split("@")[-1]
        record("PASS", f"connected to {safe}")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "could not connect", exc)


def check_mail(recipient=None):
    print("\nMail")
    if not Config.SMTP_HOST:
        record("FAIL", "LAIF_SMTP_HOST is unset",
               "Passcodes and password-reset links cannot be delivered, so members "
               "will not be able to change their details or recover an account.")
        return

    mode = "implicit SSL" if Config.SMTP_USE_SSL else (
        "STARTTLS" if Config.SMTP_USE_TLS else "no encryption")
    record("PASS" if Config.SMTP_USE_SSL or Config.SMTP_USE_TLS else "FAIL",
           f"{Config.SMTP_HOST}:{Config.SMTP_PORT} using {mode}",
           "" if Config.SMTP_USE_SSL or Config.SMTP_USE_TLS
           else "The password would cross the network in clear text.")
    print(f"          user={Config.SMTP_USER or '(none)'} password={mask(Config.SMTP_PASSWORD)}")
    print(f"          from={Config.MAIL_SENDER}")

    import smtplib
    import ssl

    context = ssl.create_default_context()
    if not Config.SMTP_VERIFY_CERT:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        record("WARN", "certificate verification is off (LAIF_SMTP_VERIFY_CERT=0)")

    try:
        if Config.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20,
                                      context=context)
        else:
            server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20)
        with server:
            if not Config.SMTP_USE_SSL and Config.SMTP_USE_TLS:
                server.starttls(context=context)
                server.ehlo()
            record("PASS", "connected and negotiated encryption")
            if Config.SMTP_USER:
                server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                record("PASS", "credentials accepted")
            else:
                record("WARN", "no LAIF_SMTP_USER, sending unauthenticated")

            if recipient:
                from email.message import EmailMessage
                message = EmailMessage()
                message["Subject"] = "LAIF deployment check"
                message["From"] = Config.MAIL_SENDER
                message["To"] = recipient
                message.set_content(
                    "This is the LAIF Community deployment check.\n\n"
                    "If you are reading it, passcodes and password-reset links "
                    "will reach your members.\n"
                )
                server.send_message(message)
                record("PASS", f"test message accepted for {recipient}",
                       "Check the inbox, and the spam folder.")
    except smtplib.SMTPAuthenticationError as exc:
        record("FAIL", "the mail server rejected the credentials", exc)
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "mail check failed", traceback.format_exc(limit=1).strip())


def main():
    recipient = sys.argv[1] if len(sys.argv) > 1 else None
    print("=" * 66)
    print("LAIF deployment check")
    print("=" * 66)
    check_settings()
    check_database()
    check_mail(recipient)

    failures = [label for level, label in results if level == "FAIL"]
    warnings = [label for level, label in results if level == "WARN"]
    print("\n" + "=" * 66)
    if failures:
        print(f"{RED}{len(failures)} problem(s) to fix before going live:{RESET}")
        for label in failures:
            print(f"  - {label}")
    else:
        print(f"{GREEN}Ready. No blocking problems found.{RESET}")
    if warnings:
        print(f"{YELLOW}{len(warnings)} warning(s):{RESET}")
        for label in warnings:
            print(f"  - {label}")
    if not recipient:
        print("\nPass an email address to send a real test message:")
        print("  python check_deploy.py you@example.com")
    print("=" * 66)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
