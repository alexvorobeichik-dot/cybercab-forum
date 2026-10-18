# Cybercab Forum

Member forum for teslacybercabforum.com. Independent, not affiliated with Tesla.

One Python file on the standard library: no framework, no bundler, no pip
packages. SQLite-backed accounts, sessions, discussions and replies.

## Run it locally

Python 3.11 or newer. Nothing else to install.

```powershell
python server.py
```

Then open http://127.0.0.1:8088.

Environment variables: `HOST` (default 127.0.0.1), `PORT` (8088), `FORUM_DB`
(database path), `FORUM_SECURE` (set to 1 behind production HTTPS),
`FORUM_REGISTRATION_OPEN` (1 to accept new accounts; 0 by default),
`FORUM_SITE_URL` (canonical origin used for links, canonical tags, Open Graph
and the sitemap; defaults to `https://teslacybercabforum.com`).

## Included

- SQLite-backed accounts, sessions, discussions and replies
- scrypt password hashes with a per-user salt, and a dummy hash computed for
  unknown usernames so sign-in timing does not reveal which accounts exist
- HttpOnly, SameSite=Lax session cookies, Secure when `FORUM_SECURE=1`
- CSRF checks on every authenticated write, escaped post output, CSP and
  frame-denial headers, cross-origin POST rejection
- Rate limiting on sign-in, registration and writes, keyed on `CF-Connecting-IP`
  and `True-Client-IP`, which Cloudflare overwrites and a client therefore
  cannot forge. `X-Forwarded-For` is only a fallback: Cloudflare appends its own
  edge address to it, so its last entry changes on every request, and a client
  can prepend anything it likes to the front
- Category browsing and search
- Authors can edit their own topics and replies, and the post shows when it was
  last edited. A moderator can lock or delete a post but **cannot rewrite it** —
  only its author can change what it says. A moderator quietly editing someone
  else's words would be worse than having no editing at all
- Moderator topic locking and deletion, with confirmation
- Responsive dark interface, guidelines/privacy page and independence
  disclaimer
- RSS. `/feed.xml` carries the whole forum, topics and replies together, and
  `/topic/N/feed.xml` carries a single discussion. Both are advertised with
  `rel=alternate` links so a reader finds them unaided, and replies carry
  anchors so a feed entry lands on the reply itself rather than the top of the
  thread
- Two sourced reference pages, built to be cited rather than to be read once.
  `/service-areas` lists every market where the robotaxi carries passengers,
  which of them have Cybercab (currently one), and which are approved but not
  launched. `/regulations` tracks the NHTSA audit of the Cybercab's
  self-certification alongside the state-by-state picture. Every row carries a
  named source and a test enforces that, because a single unsourced number would
  undermine a page whose only purpose is to be trusted. Edit the tables in
  `server.py` and bump `REFERENCE_UPDATED`, which is displayed on both pages
- Server-rendered pages, so threads are readable by search engines
- No fabricated members, posts or activity

## Search engines

Pages are server-rendered, so crawlers see the threads without running
JavaScript. `robots.txt` allows the forum and disallows the sign-in, posting
and moderation paths. `/sitemap.xml` is generated from the database on every
request and lists the homepage, the guidelines and each topic.

Every page carries a canonical URL plus Open Graph and Twitter card tags, so a
shared link previews with a title, description and image instead of a bare URL.
Set `FORUM_SITE_URL` if the canonical origin is ever anything other than
`https://teslacybercabforum.com`, otherwise the canonicals and sitemap will
point at the wrong host.

## Moderators

Moderator access is **never granted automatically** — not even to the first
registrant. It is assigned explicitly by the operator, which is what the
`/guidelines` page tells visitors. Use the operator CLI:

```powershell
python admin.py list                     # accounts, moderator flags, post counts
python admin.py promote <username>       # grant moderator access
python admin.py demote <username>        # revoke it, refusing to remove the last moderator
python admin.py create-user <username>   # add an account while registration is closed
python admin.py reset-password <username>
python admin.py delete-user <username>   # refuses without --force if they have posted
```

The commands that need a password prompt for it and require a terminal. Without
one — a hosting shell, a scheduled job — pipe it in and pass `--stdin`:

```powershell
echo "the-new-password" | python admin.py create-user <username> --stdin
echo "the-new-password" | python admin.py reset-password <username> --stdin
```

`create-user` is how the operator's own account should be made, since the
service ships with registration closed.

Promote your own account **before** opening registration. Otherwise nobody can
lock or remove anything, and the web interface offers no way to grant it.

### Running these against the deployed service

Use the Render dashboard's **Shell** tab. A one-off job will *not* work: Render
allows a persistent disk on a single instance and a job runs in its own
container, so it sees an empty directory at the mount path rather than the live
database. A job that reports success there has written somewhere that never
touches production.

## Verification

```powershell
python -m unittest test_forum.py -v
```

53 integration tests run the real HTTP server against a temporary database.
They cover registration and its closed state, sign-in and sign-out, session
cookie flags, password hashing, self-service password change, CSRF rejection,
cross-origin rejection, publishing, replies, editing your own posts (including
that nobody else can), HTML escaping, search, moderator locking and deletion
with reply cascade, rate limiting (including the production header shape and a
forged `X-Forwarded-For`), the operator bootstrap for the first moderator, the
additive schema migration for databases that predate editing, `robots.txt`, the
sitemap, canonical and Open Graph tags, and request-size limits. The suite never
touches the real community database.

## Deployment

The application runs on Render (Python 3.13.9) at
**https://cybercab-forum.onrender.com**.

The service is a paid instance (`0.5c-512mb`) in the Ohio region, created by
hand rather than from `render.yaml`.

**Persistent storage.** Render's filesystem is ephemeral, so `FORUM_DB` has to
point inside an attached disk or every deploy, restart and spin-down destroys
every account and post. That is now the case: a 1 GB disk named `forum-data` is
mounted at `/var/lib/forum`, and `FORUM_DB` is `/var/lib/forum/forum.db`.

The failure mode is silent. With an empty database, a working disk and an
ephemeral `/tmp` path look identical from the outside, and the loss only shows
up on the deploy after you have real members. To test it: register an account,
trigger a redeploy, and check that the account is still there.

**Bootstrap, then open registration.** Promote your account with `admin.py`,
then set `FORUM_REGISTRATION_OPEN=1`. Doing it in the other order risks making
a stranger the moderator of an empty database.

`render.yaml` now describes the service as deployed, but it was not used to
create the service and is not wired up now. Confirm settings in the dashboard
rather than assuming the file is live.

### The custom domain

Both `teslacybercabforum.com` and `www.teslacybercabforum.com` are already
registered on the Render service, with `www` redirecting to the apex. They stay
unverified until DNS points at Render:

| Type | Host | Value |
| --- | --- | --- |
| `A` | `@` | `216.24.57.1` |
| `CNAME` | `www` | `cybercab-forum.onrender.com` |

Remove any `AAAA` records while you are there: Render is IPv4 only. Until the
DNS moves, the apex still serves the **static** build from the `main` branch on
GitHub Pages, and the two hosts compete for the same hostname. Retire the Pages
site only *after* the domain resolves to Render — `main` holds the `CNAME` file
and GitHub holds the Pages custom-domain setting, and deleting either before
the switch leaves the domain dark.

## Files

- `server.py` — application and schema
- `admin.py` — operator CLI for moderators and password recovery
- `test_forum.py` — end-to-end HTTP integration test
- `style.css` — responsive visual design, includes the embedded display font
- `render.yaml` — Render blueprint; describes the service but is not wired up
- `forum.db` — local data, created on startup; keep private
- `static/` — share card, forum mark, web-sized photo, font licence

## Not implemented

Deliberately absent. Worth knowing before inviting members.

- Email verification and email password reset, so a lost password means asking
  the operator to run `admin.py reset-password`
- Self-service account deletion; removal is an operator action
- Spam and bot controls beyond rate limiting
- Reporting, account suspension, and per-reply moderation. Deleting an
  individual reply is not possible at all — only a whole topic can be removed,
  which becomes awkward the first time a single spam reply needs taking down
- Email notifications. Feeds cover the "tell me when someone replies" problem
  without storing addresses, but they only help people who use a feed reader

Security and trademark review is still outstanding. The disclaimer does not
guarantee the domain is free of trademark issues, and this community must not
be presented as official Tesla support.
