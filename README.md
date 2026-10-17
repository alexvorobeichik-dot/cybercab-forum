# Cybercab Forum

A community forum for the Tesla Cybercab and the wider robotaxi rollout: service
areas, ride reports, autonomy behaviour, per-mile economics, and depot
infrastructure.

**Live site:** https://teslacybercabforum.com (GitHub Pages, https)

Static site. No framework, no bundler, no dependencies, no backend. Open it and
it works.

---

## Quick start

**Option 1 — just open it.** Open `index.html` in any modern browser.

**Option 2 — serve it locally.** If you want to test over real HTTP:

```powershell
powershell -ExecutionPolicy Bypass -File .\serve.ps1
```

Then visit <http://localhost:8080>. Pass `-Port 9000` to use a different port.

---

## Features

- **Eight categories** covering the rollout, from announcements to an off-topic lounge
- **Threads and replies** — create, read, reply, and delete your own posts
- **Upvotes** on both threads and replies, tracked per browser
- **Search** across thread titles, post bodies, and author handles
- **Member pages** listing threads started and recent replies
- **Sorting** by latest activity, heat, view count, or unanswered
- **Responsive dark UI** that works from phone width up to desktop
- **Accessible touches** — skip link, keyboard `/` to focus search, labelled controls

## Project structure

```
.
├── index.html          App shell: header, category bar, view container, sidebar
├── README.md
├── serve.ps1           Dependency-free static server (Windows PowerShell)
├── CNAME               Custom domain for GitHub Pages
└── assets/
    ├── styles.css      All styling, design tokens at the top
    ├── app.js          Router, state, rendering, and event handling
    └── seed.js         Demo threads and categories loaded on first run
```

## How it works

Hash-based routing (`#/`, `#/c/news`, `#/t/t1`, `#/new`, `#/search?q=…`) means
the site needs no server-side rewrite rules, so it works identically from the
filesystem and from static hosting.

Content lives in browser `localStorage` under the key `cybercab_forum_v1`, and
your display handle under `cybercab_forum_handle`. First visit seeds the forum
from `assets/seed.js`; everything after that is yours. If storage is
unavailable the app falls back to in-memory state for the session and says so in
the footer.

**Reset demo data** in the footer wipes local storage and reseeds.

## Demo content notice

Every thread, reply, and handle in `assets/seed.js` is **invented development
data**. It is not scraped, not quoted from real users, and does not represent
anyone's actual views. Replace it before this is presented as a real community.

## Honest limitations

These are the things standing between this and a real community. They are
deliberate trade-offs, not oversights.

- **No shared state.** There is no server, so two people on two machines see two
  separate forums. A visitor who posts from their phone will not see that post
  on their laptop. This is the single biggest limitation.
- **No real accounts.** Handles are self-declared, unverified, and there is no
  password. Anyone can edit local storage and change what they see.
- **Not indexable.** Because content is client-rendered and per-browser, search
  engines cannot read threads.
- **No moderation tooling.** There is nothing to remove spam with, because there
  is nothing shared to moderate.

## Roadmap

1. Replace the storage layer with a real API so the forum becomes genuinely shared.
2. Real authentication, moderation tools, and rate limiting.
3. Server-side rendering so threads are indexable.
4. Per-category subscriptions and email digests.

The state module (`loadState` / `saveState` in `assets/app.js`) is deliberately
isolated so step 1 is a swap rather than a rewrite.

## Previous implementation

An earlier version of this project — a Python standard-library HTTP server with
SQLite-backed accounts, sessions, scrypt password hashing, CSRF checks and
moderation — is preserved in this repository's history:

- Tag: **`v1-python-forum`**
- Branch: **`archive-python-forum`**

To restore it, check out either ref, or browse it on GitHub at
`/tree/archive-python-forum`. Its `render.yaml` targets Render, which is the
correct host for that version, since GitHub Pages cannot run a Python process.

## Deployment

Hosted on GitHub Pages from the default branch, root folder, with the custom
domain `teslacybercabforum.com` set in **Settings → Pages**. The `CNAME` file in
this repo pins the domain so it survives future deploys.

DNS at Name.com points the apex and `www` at GitHub Pages.

## Disclaimer

Independent, unaffiliated fan project. Cybercab, Robotaxi, and FSD are
trademarks of Tesla, Inc. This project is not affiliated with, endorsed by, or
sponsored by Tesla, Inc. The disclaimer does not by itself resolve trademark or
domain-name risk.
