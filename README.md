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
`FORUM_REGISTRATION_OPEN` (1 to accept new accounts; 0 by default).

## Included

- SQLite-backed accounts, sessions, discussions and replies
- scrypt password hashes with a per-user salt, and a dummy hash computed for
  unknown usernames so sign-in timing does not reveal which accounts exist
- HttpOnly, SameSite=Lax session cookies, Secure when `FORUM_SECURE=1`
- CSRF checks on every authenticated write, escaped post output, CSP and
  frame-denial headers, cross-origin POST rejection
- Rate limiting on sign-in, registration and writes, keyed on the client
  address from `X-Forwarded-For` so it works behind the hosting proxy
- Category browsing and search
- Moderator topic locking and deletion, with confirmation
- Responsive dark interface, guidelines/privacy page and independence
  disclaimer
- Server-rendered pages, so threads are readable by search engines
- No fabricated members, posts or activity

## Moderators

Moderator access is **never granted automatically** — not even to the first
registrant. It is assigned explicitly by the operator, which is what the
`/guidelines` page tells visitors. Use the operator CLI:

```powershell
python admin.py list                     # accounts, moderator flags, post counts
python admin.py promote <username>       # grant moderator access
python admin.py demote <username>        # revoke it, refusing to remove the last moderator
python admin.py reset-password <username>
```

`reset-password` prompts for the password and needs a terminal. Without one —
a hosting shell, a scheduled job — pipe it in and pass `--stdin`:

```powershell
echo "the-new-password" | python admin.py reset-password <username> --stdin
```

Promote your own account **before** opening registration. Otherwise nobody can
lock or remove anything, and the web interface offers no way to grant it.

## Verification

```powershell
python -m unittest test_forum.py -v
```

27 integration tests run the real HTTP server against a temporary database.
They cover registration and its closed state, sign-in and sign-out, session
cookie flags, password hashing, CSRF rejection, cross-origin rejection,
publishing, replies, HTML escaping, search, moderator locking and deletion with
reply cascade, rate limiting and request-size limits. The suite never touches
the real community database.

## Deployment

The application runs on Render (Python 3.13.9) at
**https://cybercab-forum.onrender.com**.

Two things have to be true before this is a public forum:

1. **Persistent storage.** Render's filesystem is ephemeral. Unless `FORUM_DB`
   points inside an attached persistent disk, every deploy, restart and idle
   spin-down destroys all accounts and posts. Disks require a paid instance
   type. Check this in the dashboard rather than assuming it: while the
   database is empty, the two states are indistinguishable from the outside.
2. **Bootstrap, then open registration.** Promote your account with `admin.py`,
   then set `FORUM_REGISTRATION_OPEN=1`. Doing it in the other order risks
   making a stranger the moderator of an empty database.

`render.yaml` in this repository names the service `teslacybercabforum`, which
does not match the deployed service name `cybercab-forum`. Treat it as a
starting point rather than a description of what is actually running, and
confirm the live environment variables directly in the dashboard.

### The custom domain

`teslacybercabforum.com` currently serves the **static** build from the `main`
branch on GitHub Pages. It does not point at this application. Repointing it
means moving the apex to Render, removing `CNAME` from `main`, and clearing the
custom domain in the repository's Pages settings so the two stop competing for
the same hostname.

## Files

- `server.py` — application and schema
- `admin.py` — operator CLI for moderators and password recovery
- `test_forum.py` — end-to-end HTTP integration test
- `style.css` — responsive visual design, includes the embedded display font
- `render.yaml` — Render blueprint, currently out of sync with the live service
- `forum.db` — local data, created on startup; keep private
- `static/` — forum mark, web-sized photo, font licence

## Not implemented

Deliberately absent. Worth knowing before inviting members.

- Email verification, email password reset, self-service account deletion
- Spam and bot controls beyond rate limiting
- Per-reply moderation, reporting, account suspension
- Sitemap or feed

Security and trademark review is still outstanding. The disclaimer does not
guarantee the domain is free of trademark issues, and this community must not
be presented as official Tesla support.
