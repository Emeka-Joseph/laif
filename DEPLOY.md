# Deploying LAIF Community on cPanel

For shared hosting with cPanel's **Setup Python App** (Namecheap, Hostinger,
Bluehost, A2 and most others). Passenger runs the app; there is no gunicorn or
nginx to configure.

Work through this in order. Step 7 is a script that proves the site is ready
before you tell anyone the address.

---

## 1. Create the database

**cPanel → MySQL® Databases**

1. Create a database, e.g. `laifuser_laifdb`.
2. Create a user with a strong password.
3. Add the user to the database with **ALL PRIVILEGES**.

Write down all three values. cPanel prefixes them with your account name, so
the real database name is longer than what you typed.

The app builds its own tables on first start — there is nothing to import.

## 2. Create the Python application

**cPanel → Setup Python App → Create Application**

| Field | Value |
|---|---|
| Python version | The newest offered (3.11+ if available; 3.9 works) |
| Application root | `laif` |
| Application URL | your domain, or a subdomain |
| Application startup file | `app.py` |
| Application entry point | `application` |

**The startup file must say `app.py`, not `passenger_wsgi.py`.** cPanel writes
its own `passenger_wsgi.py` that loads whatever name is in that box. Naming
`passenger_wsgi.py` there makes it load itself until Python raises
`RecursionError: maximum recursion depth exceeded`, and the site never starts.
The real application lives in `app.py`; the `passenger_wsgi.py` in the package is
a two-line loader that cPanel is free to overwrite.


Leave the page open — you come back to it in steps 4 and 6.

Python 3.9 is supported but reached end of life in October 2025, so it no
longer receives security fixes. If the dropdown offers 3.11 or newer, take it.


## 3. Upload the files

Upload `laif-deploy.zip` into the **Application root** from step 2 and extract
it there.

The zip is around 250 MB, almost all of it the photographs in `images/`. If
cPanel's File Manager refuses a file that size, upload it over FTP/SFTP
instead, or upload `images/` separately by FTP and the rest through the browser.

When it is extracted, `app.py` and `passenger_wsgi.py` must sit directly in the
application root — not inside a nested folder.

## 4. Set the environment variables

**Setup Python App → your app → Environment variables.** Add each one, then
press **Save**.

### Required

| Variable | Value |
|---|---|
| `LAIF_SECRET_KEY` | A long random string. Generate one and never reuse it: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `LAIF_DB_USER` | The database user from step 1 |
| `LAIF_DB_PASSWORD` | Its password |
| `LAIF_DB_NAME` | The full database name from step 1 |
| `LAIF_DB_HOST` | `localhost` |
| `LAIF_ADMIN_EMAIL` | The address you want to sign in to `/admin/login` with |
| `LAIF_ADMIN_PASSWORD` | A strong password for that account |
| `LAIF_OTP_SHOW_IN_UI` | `0` |

`LAIF_OTP_SHOW_IN_UI=0` matters: left on, the site prints passcodes and
password-reset links in the browser whenever email delivery fails, which would
let anyone take over a member's account.

`LAIF_ADMIN_PASSWORD` matters for the same reason. Without it the administrator
is created with the password published in this repository.

### Mail — required for passcodes and password resets

Members cannot change their profile or recover a forgotten password unless mail
works, so treat these as required too.

**Using the domain's own mailbox (recommended on cPanel):** create the address
first under **cPanel → Email Accounts**.

| Variable | Value |
|---|---|
| `LAIF_SMTP_HOST` | `mail.yourdomain.org` |
| `LAIF_SMTP_PORT` | `465` |
| `LAIF_SMTP_USER` | `office@yourdomain.org` |
| `LAIF_SMTP_PASSWORD` | That mailbox's password |
| `LAIF_MAIL_SENDER` | `office@yourdomain.org` |

**Using Gmail instead:** `LAIF_SMTP_HOST=smtp.gmail.com`, `LAIF_SMTP_PORT=587`,
`LAIF_SMTP_USER=laifoffice2020@gmail.com`, and for `LAIF_SMTP_PASSWORD` a
16-character **App Password** — not the account password. App Passwords need
2-Step Verification switched on, at
<https://myaccount.google.com/apppasswords>. Some shared hosts block outbound
connections to other providers; if Gmail times out in step 7, use the domain
mailbox above.

Port 465 and port 587 speak different dialects, and the app picks the right one
from the port number, so setting `LAIF_SMTP_PORT` correctly is normally all
that is needed. Two escape hatches exist if your host is unusual:

| Variable | When to use it |
|---|---|
| `LAIF_SMTP_SSL` | `1` forces port-465 style, `0` forces STARTTLS. Only if the port default is wrong for your server. |
| `LAIF_SMTP_VERIFY_CERT` | `0` if the mail server presents a self-signed certificate and step 7 reports a certificate error. Leave it unset otherwise. |

## 5. Install the dependencies

On the **Setup Python App** page, copy the command shown at the top — it looks
like `source /home/USER/virtualenv/laif/3.11/bin/activate && cd /home/USER/laif`.

**cPanel → Terminal**, paste it, then:

```bash
pip install -r requirements.txt
```

Only Flask, Flask-SQLAlchemy and PyMySQL are pinned. Their own dependencies
are left to pip, so the same file works whatever Python version cPanel gave
you — on 3.9 it selects `click` 8.1.8, on 3.11+ it selects 8.5.0.

Once the install succeeds, lock the exact set for next time:

```bash
pip freeze > requirements.lock.txt
```

Keep that file on the server. A lock file only describes the machine it was
generated on, so one written on a Windows laptop will not install here.

If your host has no Terminal, put `requirements.txt` in the **Configuration
files** box on the Setup Python App page and press **Run Pip Install**.

## 6. Start it

Press **Restart** on the Setup Python App page, then open your domain.

## 7. Check it before announcing it

In Terminal, with the virtualenv still active:

```bash
python check_deploy.py
```

It reads exactly what the running site reads, and reports on the secret key,
the admin password, the passcode setting, the uploads folder, the database
connection and the mail server. Fix anything marked `FAIL` and run it again.

When it is clean, send yourself a real message:

```bash
python check_deploy.py you@example.com
```

A `PASS` on that line means the mail server accepted the message — check the
inbox, and the spam folder, to confirm it arrived. Passcodes and password-reset
links travel the same path, so if that message lands, they will too.

## 8. Sign in and change what the seed created

Go to `/admin/login` and sign in with `LAIF_ADMIN_EMAIL` and
`LAIF_ADMIN_PASSWORD`.

The first start also seeds three sample resources and one sample blog post
("There is more grace for today"). Edit or delete them from the admin panel.

---

## Afterwards

**Uploading new code.** Replace the changed files, then press **Restart** on the
Setup Python App page. Passenger keeps the old code in memory until you do.

**Anything the app writes.** `laif_app/static/uploads/` holds members' portfolio
photographs and profile pictures. It is not in the zip beyond an empty
placeholder and it is excluded from git, so **back it up separately** — with the
database — before any redeploy. Everything else can be rebuilt from the
repository.

**Database changes.** There is no migration tool. `laif_app/seed.py` runs
`sync_columns()` at every start, which adds columns a model gained but the table
lacks. It only ever adds; renaming or retyping a column is a manual job.

**Serving the photographs faster.** Every image currently passes through Python.
If the site feels slow, an `.htaccess` in the application root will hand
`/images` and `/static` straight to Apache:

```apache
RewriteEngine On
RewriteRule ^(images|laif_app/static)/ - [L]
```

**If the log fills with `RecursionError: maximum recursion depth exceeded`**, and
the repeated line is `imp.load_source('wsgi', 'passenger_wsgi.py')`. The
Application startup file is set to `passenger_wsgi.py`, so cPanel's stub is
loading itself. Set it to `app.py` and press Restart.

**If pip reports "Could not find a version that satisfies...".** A pinned
version does not exist for this server's Python. The version list in the error
shows what is available; the highest entry that pip did not reject is the one to
use. `ERROR: Ignored the following versions that require a different python
version` names the interpreter's limit.

**If the site shows a 500.** Read `stderr.log` in the application root — the
warnings from `passenger_wsgi.py` about unset variables appear there too.

## Known limits

- `MAX_CONTENT_LENGTH` is 64 MB, but shared hosts often cap uploads lower. If
  large video uploads fail with a server error rather than the app's own "file
  is too large" message, the host's limit is the one being hit.
- Sign-up does not enforce a minimum password length; password *reset* requires
  eight characters. Worth making consistent when you next touch that code.
