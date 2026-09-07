# LAIF Community

A Flask-based church community website for Life Abundant International Church.

## Run locally

```powershell
python -m pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000`. The admin panel lives at `http://127.0.0.1:5000/admin/login`.

## Project structure

```
run.py                  entry point (creates the app via the factory)
config.py               paths, resource constants and the Config class
laif_app/
├── __init__.py         create_app() application factory
├── extensions.py       shared SQLAlchemy instance
├── models.py           User, Post, Comment, Resource, ContactMessage, AccessCode,
│                       PortfolioWork, PortfolioItem, WorkLink, MemberLink,
│                       OtpChallenge
├── helpers.py          current_user(), admin_required, login_required, upload handling
├── otp.py              one-time passcodes guarding profile changes
├── seed.py             first-run seeding and additive column sync
├── templates/          shared layout (base.html)
├── static/             css, js, docs, uploads
├── user/               public site blueprint
│   ├── __init__.py     user_bp
│   ├── routes.py
│   └── templates/user/
└── admin/              admin blueprint (url_prefix="/admin")
    ├── __init__.py     admin_bp
    ├── routes.py
    └── templates/admin/
```

## The member dashboard

Signed-in members land on `/dashboard`, where they can:

- **Edit their profile** — name, email, phone number, address, city, country, skills, short bio
  and profile picture.
- **List where to find them online** — their own website and social media handles, under
  **Find me online**, shown as chips at the top of their public profile. These belong to the
  person rather than to any one job, so they stay put as pieces of work come and go, and unlike
  the profile fields above they save without a passcode: they are public showcase links, not
  details the account is recovered with, and removing one is a single click.
- **List their previous work** — **Add new work** creates an entry for a job they have done,
  with a title, client, date, a one-line summary, the full story, its first pictures, and a
  **Websites & social media** panel for links out. Each job is then managed on its own page at
  `/dashboard/works/<id>`, where **Add new image** uploads as many photos and clips as the job
  needs (several at once) and captions them, and where more links are added or removed.

Every link form on the site — the profile's, the one inside "add new work", and the job's own
page — sends the same repeating `link_label` / `link_url` pair and is read by `_read_links()`.
`+ Add another link` clones the row so several addresses go in at once, up to eight per job and
eight per profile; that button is revealed by JavaScript, so with scripting off the single row
still submits normally. A job's links show as pills on its dashboard row.

Addresses are stored as plain `http(s)` only. `instagram.com/handle` has its scheme filled in;
anything else — a `javascript:` payload, say — is refused and named in the message, without
discarding the good rows submitted alongside it. Every link renders with
`rel="noopener noreferrer"`.

Visitors browse a member at `/members/<id>`, reached from the Skills &amp; talents directory. The
profile shows one tile per job — cover photo, title, client and date; clicking a tile opens
`/members/<id>/work/<work_id>` with that job's whole gallery, its full description, its links,
and a step across to the member's other work. Clicking any photo or clip there opens it full
size in a lightbox; the arrow keys or the on-screen chevrons move between items, and Escape or
a click on the backdrop closes it again.

### Passcode verification

Profile *field* changes are never written straight to the database (the **Find me online**
links are the exception noted above). The submitted values (and any new
picture, stored under a random name) are parked on an `OtpChallenge` row alongside a hashed
six-digit code, and only copied onto the account once the member types that code back at
`/dashboard/verify`. Abandoning or cancelling the change leaves the profile untouched.

Codes expire after 10 minutes, allow 5 attempts, and can be re-sent after 45 seconds — all
configurable at the top of `config.py`.

Delivery is by email. Set these environment variables to use a real mail server:

```powershell
$env:LAIF_SMTP_HOST = "smtp.gmail.com"
$env:LAIF_SMTP_PORT = "587"
$env:LAIF_SMTP_USER = "laifoffice2020@gmail.com"
$env:LAIF_SMTP_PASSWORD = "<app password>"
$env:LAIF_MAIL_SENDER = "laifoffice2020@gmail.com"
```

With no `LAIF_SMTP_HOST` set the code is written to the application log and shown on the verify
screen, so the flow stays usable in development. **Set `LAIF_OTP_SHOW_IN_UI=0` before deploying**
so passcodes are never displayed in the browser.

`laif_app/otp.py` has a `send_sms()` stub — wire a gateway such as Twilio there to send codes to
a member's phone instead, and pass `channel="sms"` when creating the challenge.

### Uploads

Portfolio media lands in `laif_app/static/uploads/` under a random filename.

| | Formats | Limit |
|---|---|---|
| Images | jpg, jpeg, png, webp, gif | 8 MB |
| Videos | mp4, webm, mov, m4v | 60 MB |

A member may list up to 20 pieces of work, holding up to 15 files each and 40 files in total,
with up to 8 links per job and 8 on the profile itself. Deleting a job removes its pictures from disk along with it, as does
removing a single picture or replacing a profile photo. Limits live in `config.py`;
`MAX_CONTENT_LENGTH` is the hard ceiling Flask enforces before a request reaches a view, and a
413 handler turns that into a friendly message.

### Schema changes

The project has no migration tool. `seed.py` calls `sync_columns()` on start-up, which compares
each table against the models and issues `ALTER TABLE ... ADD COLUMN` for anything missing, so an
existing database picks up the new profile fields on the next run. It is additive only — nothing
is dropped or retyped.

`backfill_works()` runs straight after it. Portfolio photos uploaded before jobs existed have no
job to belong to, so each one is wrapped in a piece of work carrying its old title, description
and date. Nothing is lost, and a member can merge those entries afterwards from the dashboard.

## The admin panel

`/admin/dashboard` opens on a row of counters — members, posts, resources, unused invitation
codes, contact inquiries — followed by the newest members, the posts table and the inquiry inbox,
each in its own panel. The counters for members and codes are links through to those screens.

### Registered members

**View all members** (`/admin/members`) lists every account, newest first, with avatar, name,
skills, email, phone, location and a role pill. A search box matches name, email, phone, skills
or location, and a dropdown filters by role. Each row carries **View** and **Delete**.

`/admin/members/<id>` shows one account in full: name, email, phone, address, city, country,
skills, bio, role, their websites and social handles, and a sidebar listing their previous work
and file count.

**Passwords are never shown.** Only a hash is stored, and no admin view reads `password_hash` —
the detail page prints "Stored as a hash — never shown" in its place. A member who is locked out
resets their own at `/forgot-password`.

Deleting an account removes its previous work, portfolio pictures, profile links and pending
passcode challenges through the database cascades, and clears the profile picture and every
uploaded file from `static/uploads/`. Three cases are refused with an explanation rather than a
database error, in `_delete_blocker()`:

- your own account, so an admin cannot sign themselves out of the panel;
- any other administrator account, so the panel cannot be emptied of admins;
- an account that has authored blog posts, which would leave those posts without an author.

Both list and detail pages disable the delete button in those cases, and the route checks again
before acting — the button is a convenience, not the guard.

## Accounts

The app creates the database automatically and seeds starter resources, a sample post, and an admin account:

- Email: `admin@laifcommunity.org`
- Password: `ChangeMe123!`

Change the default password before deploying. Members join with a one-time invitation code generated by the
admin at `/admin/codes`. The admin manages all blog posts and resources.

Images are served from the supplied `images` folder. Facebook and YouTube destinations in the Live page are
intentionally placeholders for the church's final stream URLs.
