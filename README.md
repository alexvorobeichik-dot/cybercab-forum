# Cybercab Forum

Working local member-forum MVP for teslacybercabforum.com. Independent, not affiliated with Tesla.

## Start on this Windows computer
From this folder run `runtime\python.exe server.py`, then open http://127.0.0.1:8088 . A portable Python 3.13.9 runtime was downloaded from python.org into runtime; no global installation was changed.

On another system with Python 3.11+ run `python server.py`. No pip packages required.

## Included
- SQLite-backed accounts, sessions, discussions and replies
- scrypt password hashes; HTTP-only same-site session cookies; CSRF checks on authenticated actions; escaped post output
- Category browsing and search
- Moderator topic locking and deletion with confirmation
- Responsive dark interface, guidelines/privacy page and independence disclaimer
- No fabricated members, posts or activity

The first registered account becomes administrator. Create your own account while the server is still local, before exposing the site publicly. No default password exists.

## Verification
Run `runtime\python.exe -m unittest test_forum.py -v` (or `python -m unittest test_forum.py -v`). The integration test uses a temporary database and verifies registration, login/logout, publishing, replies, escaping, CSRF rejection, locking and deletion. It does not populate the real community database.

## Public deployment: not completed
The domain returned ERR_SSL_TLSV1_UNRECOGNIZED_NAME during the HTTPS check. No registrar or hosting account was connected. Nothing has been deployed to that domain, and DNS has not been changed.

This is an MVP, not a hardened public production service. Before inviting members:
1. Provision a Python host/VPS with persistent disk. This standard-library HTTP server is for local evaluation; use a production server/reverse proxy strategy with process supervision, connection/time limits and request limits.
2. Run the application as a nonprivileged user bound to localhost. Set PORT if needed. Keep forum.db on persistent storage; back it up securely and test restoration.
3. Configure a TLS reverse proxy for teslacybercabforum.com and point the domain's DNS to that host. Set FORUM_SECURE=1 so cookies are HTTPS-only; never disable this for public use.
4. Register your administrator locally before public exposure. Add a real operator contact to the privacy/guidelines page and publish retention, deletion and abuse-reporting procedures appropriate to your jurisdiction.
5. Add rate limiting and bot/spam controls before enabling public registration. Implement password reset/email verification, account suspension, report handling, per-reply moderation, account deletion and admin recovery. They are not implemented in this MVP.
6. Review security and trademark/domain risks. The disclaimer does not guarantee the domain is free of trademark issues. Do not present this community as official Tesla support.
7. Verify HTTPS, cookies, registration, moderation, mobile layouts, backups and recovery on the deployed host before promotion.

## Files
- server.py — application and schema
- style.css — responsive visual design
- test_forum.py — end-to-end HTTP integration test
- forum.db — local data, created on startup; keep private
- runtime/ — portable Windows Python runtime, not required on a host with Python installed

Environment variables: HOST (default 127.0.0.1), PORT (8088), FORUM_DB (database path), FORUM_SECURE (set 1 behind production HTTPS).
