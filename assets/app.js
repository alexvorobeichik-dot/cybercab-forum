/* ==========================================================================
   Cybercab Forum — application logic
   --------------------------------------------------------------------------
   No dependencies, no build step, no server. Router is hash based so the site
   works when opened straight from the filesystem (file://) and when hosted on
   GitHub Pages without any rewrite rules.
   ========================================================================== */

(function () {
  "use strict";

  var STORAGE_KEY = "cybercab_forum_v1";
  var HANDLE_KEY = "cybercab_forum_handle";

  /* --------------------------------------------------------------- storage */

  var memory = {};

  var storageWorks = (function () {
    try {
      var probe = "__cybercab_probe__";
      window.localStorage.setItem(probe, "1");
      window.localStorage.removeItem(probe);
      return true;
    } catch (err) {
      return false;
    }
  })();

  function storeGet(key) {
    if (storageWorks) {
      try { return window.localStorage.getItem(key); } catch (err) { return null; }
    }
    return Object.prototype.hasOwnProperty.call(memory, key) ? memory[key] : null;
  }

  function storeSet(key, value) {
    if (storageWorks) {
      try { window.localStorage.setItem(key, value); return; } catch (err) { /* quota */ }
    }
    memory[key] = String(value);
  }

  function storeRemove(key) {
    if (storageWorks) {
      try { window.localStorage.removeItem(key); return; } catch (err) { /* ignore */ }
    }
    delete memory[key];
  }

  /* --------------------------------------------------------------- helpers */

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function uid(prefix) {
    return (prefix || "id") + "_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function timeAgo(ts) {
    var seconds = Math.max(1, Math.floor((Date.now() - ts) / 1000));
    if (seconds < 60) return seconds + "s ago";
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + "m ago";
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + "h ago";
    var days = Math.floor(hours / 24);
    if (days < 30) return days + "d ago";
    var months = Math.floor(days / 30);
    if (months < 12) return months + "mo ago";
    return Math.floor(months / 12) + "y ago";
  }

  function fullDate(ts) {
    try { return new Date(ts).toLocaleString(); } catch (err) { return ""; }
  }

  function paragraphs(text) {
    return esc(text)
      .split(/\n{2,}/)
      .map(function (block) { return "<p>" + block.replace(/\n/g, "<br />") + "</p>"; })
      .join("");
  }

  function truncate(text, max) {
    var flat = String(text || "").replace(/\s+/g, " ").trim();
    return flat.length > max ? flat.slice(0, max - 1) + "\u2026" : flat;
  }

  function avatarStyle(handle) {
    var name = String(handle || "?"), h = 0;
    for (var i = 0; i < name.length; i++) { h = (h * 31 + name.charCodeAt(i)) % 360; }
    return "background:linear-gradient(160deg,hsl(" + h + ",74%,74%),hsl(" + ((h + 42) % 360) + ",66%,58%))";
  }

  function avatarLabel(handle) {
    var name = String(handle || "?").replace(/[^a-z0-9]/gi, "");
    return (name.slice(0, 2) || "?").toUpperCase();
  }

  function avatarHtml(handle, large) {
    return '<span class="avatar' + (large ? " avatar-lg" : "") + '" style="' + avatarStyle(handle) + '">' +
      esc(avatarLabel(handle)) + "</span>";
  }

  function byId(list, id) {
    for (var i = 0; i < list.length; i++) { if (list[i].id === id) return list[i]; }
    return null;
  }

  function param(name) {
    var match = new RegExp("[?&]" + name + "=([^&]*)").exec(window.location.hash);
    return match ? decodeURIComponent(match[1].replace(/\+/g, " ")) : "";
  }

  function parseHash() {
    var raw = window.location.hash.replace(/^#/, "");
    if (!raw) raw = "/";
    var questionAt = raw.indexOf("?");
    var path = questionAt === -1 ? raw : raw.slice(0, questionAt);
    var segments = path.split("/").filter(function (s) { return s.length > 0; });
    return { path: path, segments: segments };
  }

  function go(hash) {
    if (window.location.hash === hash) { render(); return; }
    window.location.hash = hash;
  }

  /* ----------------------------------------------------------------- state */

  var state = null;
  var ui = { sort: "latest" };
  var viewedThisSession = {};
  var lastPath = null;

  function buildFromSeed() {
    var now = Date.now();
    var hour = 3600000;
    var threads = [];
    var posts = [];

    window.SEED.threads.forEach(function (source) {
      threads.push({
        id: source.id,
        cat: source.cat,
        title: source.title,
        body: source.body,
        author: source.author,
        createdAt: now - source.hoursAgo * hour,
        pinned: !!source.pinned,
        views: source.views || 0,
        votes: source.votes || 0
      });

      (source.replies || []).forEach(function (reply, index) {
        posts.push({
          id: source.id + "_r" + (index + 1),
          threadId: source.id,
          author: reply.author,
          body: reply.body,
          createdAt: now - reply.hoursAgo * hour,
          votes: reply.votes || 0
        });
      });
    });

    return { version: 1, seededAt: now, threads: threads, posts: posts, myVotes: {} };
  }

  function loadState() {
    var raw = storeGet(STORAGE_KEY);
    if (raw) {
      try {
        var parsed = JSON.parse(raw);
        if (parsed && parsed.threads && parsed.posts) {
          if (!parsed.myVotes) parsed.myVotes = {};
          return parsed;
        }
      } catch (err) { /* corrupt payload, fall through and reseed */ }
    }
    var fresh = buildFromSeed();
    storeSet(STORAGE_KEY, JSON.stringify(fresh));
    return fresh;
  }

  function saveState() {
    storeSet(STORAGE_KEY, JSON.stringify(state));
  }

  /* -------------------------------------------------------------- identity */

  function myHandle() { return storeGet(HANDLE_KEY) || ""; }

  function ensureHandle(force) {
    var current = myHandle();
    if (current && !force) return current;

    var entered = window.prompt("Choose a display handle. It appears on everything you post.", current || "");
    if (entered === null) return current;

    entered = entered.trim().replace(/\s+/g, "_").replace(/[^A-Za-z0-9._-]/g, "").slice(0, 24);
    if (!entered) return current;

    storeSet(HANDLE_KEY, entered);
    refreshIdentity();
    return entered;
  }

  function refreshIdentity() {
    var nameEl = document.getElementById("identity-name");
    var avatarEl = document.getElementById("identity-avatar");
    if (!nameEl || !avatarEl) return;

    var handle = myHandle();
    if (handle) {
      nameEl.textContent = handle;
      avatarEl.textContent = avatarLabel(handle);
      avatarEl.setAttribute("style", avatarStyle(handle));
    } else {
      nameEl.textContent = "Set handle";
      avatarEl.textContent = "?";
      avatarEl.setAttribute("style", "background:#2a2f38;color:#b3b9c4");
    }
  }

  /* --------------------------------------------------------------- derived */

  function postsFor(threadId) {
    return state.posts
      .filter(function (p) { return p.threadId === threadId; })
      .sort(function (a, b) { return a.createdAt - b.createdAt; });
  }

  function categoryById(id) { return byId(window.SEED.categories, id); }

  function threadStats(thread) {
    var posts = postsFor(thread.id);
    return {
      replies: posts.length,
      last: posts.length ? posts[posts.length - 1].createdAt : thread.createdAt,
      lastAuthor: posts.length ? posts[posts.length - 1].author : thread.author
    };
  }

  function memberCount() {
    var seen = {};
    state.threads.forEach(function (t) { seen[t.author] = true; });
    state.posts.forEach(function (p) { seen[p.author] = true; });
    return Object.keys(seen).length;
  }

  function sortedThreads(list, sort) {
    var pinned = [];
    var rest = [];

    list.forEach(function (thread) { (thread.pinned ? pinned : rest).push(thread); });

    rest.sort(function (a, b) {
      if (sort === "hot") {
        return (b.votes + threadStats(b).replies * 4) - (a.votes + threadStats(a).replies * 4);
      }
      if (sort === "views") return b.views - a.views;
      if (sort === "unanswered") {
        var diff = threadStats(a).replies - threadStats(b).replies;
        return diff !== 0 ? diff : b.createdAt - a.createdAt;
      }
      return threadStats(b).last - threadStats(a).last;
    });

    return pinned.concat(rest);
  }

  /* ------------------------------------------------------- shared fragments */

  function sortSeg(current) {
    var options = [["latest", "Latest"], ["hot", "Hot"], ["views", "Most viewed"], ["unanswered", "Unanswered"]];
    return '<div class="seg">' + options.map(function (pair) {
      return '<button type="button" data-action="sort" data-value="' + pair[0] + '"' +
        (current === pair[0] ? ' class="is-active"' : "") + ">" + pair[1] + "</button>";
    }).join("") + "</div>";
  }

  function threadRow(thread) {
    var cat = categoryById(thread.cat);
    var stats = threadStats(thread);
    var hot = stats.replies >= 3 && (Date.now() - stats.last) < 12 * 3600000;

    return '<a class="thread-row" href="#/t/' + esc(thread.id) + '">' +
      avatarHtml(thread.author) +
      '<div class="thread-main">' +
        '<span class="thread-title">' + esc(thread.title) + "</span>" +
        '<div class="thread-snippet">' + esc(truncate(thread.body, 150)) + "</div>" +
        '<div class="meta">' +
          (cat ? '<span class="cat-tag"><span class="swatch" style="background:' + esc(cat.color) + '"></span>' + esc(cat.name) + '</span><span class="sep">\u00b7</span>' : "") +
          "<span>" + esc(thread.author) + "</span>" +
          '<span class="sep">\u00b7</span><span>' + timeAgo(thread.createdAt) + "</span>" +
          (thread.pinned ? '<span class="badge badge-pinned">Pinned</span>' : "") +
          (hot ? '<span class="badge badge-hot">Hot</span>' : "") +
        "</div>" +
      "</div>" +
      '<div class="thread-side"><b>' + stats.replies + "</b>replies" +
        "<div>" + thread.views.toLocaleString() + " views</div>" +
        "<div>" + timeAgo(stats.last) + "</div>" +
      "</div>" +
    "</a>";
  }

  function threadListCard(threads) {
    return '<div class="card"><div class="thread-list">' +
      threads.map(threadRow).join("") +
      "</div></div>";
  }

  function postHtml(post, isOp) {
    var voted = !!state.myVotes["p:" + post.id];
    var mine = post.author === myHandle();

    return '<article class="post' + (isOp ? " is-op" : "") + '">' +
      avatarHtml(post.author, true) +
      "<div>" +
        '<div class="post-head">' +
          '<span class="post-author">' + esc(post.author) + "</span>" +
          (isOp ? '<span class="badge">Original post</span>' : "") +
          '<time title="' + esc(fullDate(post.createdAt)) + '">' + timeAgo(post.createdAt) + "</time>" +
        "</div>" +
        '<div class="post-body">' + paragraphs(post.body) + "</div>" +
        '<div class="post-foot">' +
          '<button class="votebtn' + (voted ? " is-voted" : "") + '" type="button" data-action="vote-post" data-id="' + esc(post.id) + '">' +
            '\u25b2 <span class="vote-count">' + post.votes + "</span>" +
          "</button>" +
          (mine ? '<button class="linkbtn" type="button" data-action="delete-post" data-id="' + esc(post.id) + '">Delete</button>' : "") +
        "</div>" +
      "</div>" +
    "</article>";
  }

  function notFound(message) {
    return '<div class="card"><div class="empty">' +
      "<h3>Nothing here</h3>" +
      "<p>" + esc(message) + "</p>" +
      '<a class="btn btn-primary" href="#/">Back to the forum</a>' +
    "</div></div>";
  }

  /* ------------------------------------------------------------ view: home */

  function viewHome() {
    var threads = sortedThreads(state.threads, ui.sort);

    return '<section class="hero">' +
      "<h1>The Tesla Cybercab community</h1>" +
      "<p>A forum for people following the robotaxi rollout: service areas, ride reports, autonomy behaviour, per-mile economics, and depot infrastructure. Static site, no accounts required, nothing phoned home.</p>" +
      '<div class="hero-stats">' +
        '<div class="hero-stat"><b>' + state.threads.length + "</b><span>Threads</span></div>" +
        '<div class="hero-stat"><b>' + state.posts.length + "</b><span>Replies</span></div>" +
        '<div class="hero-stat"><b>' + memberCount() + "</b><span>Members</span></div>" +
      "</div>" +
    "</section>" +
    '<div class="toolbar">' +
      '<h2 style="font-size:16px;margin:0">Latest discussions</h2>' +
      sortSeg(ui.sort) +
    "</div>" +
    (threads.length ? threadListCard(threads) : notFound("No threads yet."));
  }

  /* -------------------------------------------------------- view: category */

  function viewCategory(id) {
    var cat = categoryById(id);
    if (!cat) return notFound("That category does not exist.");

    var threads = state.threads.filter(function (t) { return t.cat === id; });

    var html = '<div class="crumbs">' +
      '<a href="#/">Forum</a><span class="sep">/</span><span>' + esc(cat.name) + "</span>" +
    "</div>" +
    '<h1 class="page-title">' + esc(cat.name) + "</h1>" +
    '<p class="page-sub">' + esc(cat.blurb) + "</p>" +
    '<div class="toolbar">' +
      '<span style="font-size:12.5px;color:var(--muted)">' + threads.length + " thread" + (threads.length === 1 ? "" : "s") + "</span>" +
      sortSeg(ui.sort) +
    "</div>";

    html += threads.length
      ? threadListCard(sortedThreads(threads, ui.sort))
      : '<div class="card"><div class="empty"><h3>Nothing here yet</h3><p>Be the first to start a discussion in ' +
        esc(cat.name) + ".</p><a class=\"btn btn-primary\" href=\"#/new?cat=" + esc(cat.id) + '">Start a thread</a></div></div>';

    return html;
  }

  /* ---------------------------------------------------------- view: thread */

  function viewThread(id) {
    var thread = byId(state.threads, id);
    if (!thread) return notFound("That thread does not exist.");

    if (!viewedThisSession[thread.id]) {
      viewedThisSession[thread.id] = true;
      thread.views += 1;
      saveState();
    }

    var cat = categoryById(thread.cat);
    var posts = postsFor(thread.id);
    var voted = !!state.myVotes["t:" + thread.id];
    var handle = myHandle();

    var html = '<div class="crumbs">' +
      '<a href="#/">Forum</a><span class="sep">/</span>' +
      (cat ? '<a href="#/c/' + esc(cat.id) + '">' + esc(cat.name) + '</a><span class="sep">/</span>' : "") +
      "<span>" + esc(truncate(thread.title, 46)) + "</span>" +
    "</div>";

    html += '<article class="card" style="margin-bottom:18px"><div class="post is-op">' +
      avatarHtml(thread.author, true) +
      "<div>" +
        '<div class="post-head">' +
          '<span class="post-author">' + esc(thread.author) + "</span>" +
          (thread.pinned ? '<span class="badge badge-pinned">Pinned</span>' : "") +
          '<time title="' + esc(fullDate(thread.createdAt)) + '">' + timeAgo(thread.createdAt) + "</time>" +
        "</div>" +
        '<h1 style="font-size:20px;margin:8px 0 14px">' + esc(thread.title) + "</h1>" +
        '<div class="post-body">' + paragraphs(thread.body) + "</div>" +
        '<div class="post-foot">' +
          '<button class="votebtn' + (voted ? " is-voted" : "") + '" type="button" data-action="vote-thread" data-id="' + esc(thread.id) + '">' +
            '\u25b2 <span class="vote-count">' + thread.votes + "</span>" +
          "</button>" +
          '<span class="meta" style="margin-left:8px">' +
            "<span>" + thread.views.toLocaleString() + " views</span>" +
            '<span class="sep">\u00b7</span>' +
            "<span>" + posts.length + " replies</span>" +
            '<span class="sep">\u00b7</span>' +
            '<a href="#/u/' + encodeURIComponent(thread.author) + '">View author</a>' +
          "</span>" +
        "</div>" +
      "</div>" +
    "</div></article>";

    if (posts.length) {
      html += '<div class="card" style="margin-bottom:18px">' + posts.map(function (post) {
        return postHtml(post, false);
      }).join("") + "</div>";
    } else {
      html += '<div class="card" style="margin-bottom:18px"><div class="empty"><h3>No replies yet</h3>' +
        "<p>Be the first to respond to this thread.</p></div></div>";
    }

    html += '<form class="card" data-action="reply" data-thread="' + esc(thread.id) + '">' +
      '<div class="reply-box">' +
        '<div class="field">' +
          "<label for=\"reply-body\">Reply as " + esc(handle || "a new member") + "</label>" +
          '<textarea id="reply-body" name="body" placeholder="Add to the discussion\u2026" required></textarea>' +
          '<div class="help">Blank lines create separate paragraphs. Links are shown as plain text.</div>' +
        "</div>" +
        '<div class="form-actions">' +
          '<button class="btn btn-primary" type="submit">Post reply</button>' +
          '<a class="btn btn-ghost" href="#/c/' + esc(thread.cat) + '">Back to category</a>' +
        "</div>" +
      "</div>" +
    "</form>";

    return html;
  }

  /* ------------------------------------------------------ view: new thread */

  function viewNewThread() {
    var preselect = param("cat") || (window.SEED.categories[0] && window.SEED.categories[0].id) || "";
    var handle = myHandle();

    var options = window.SEED.categories.map(function (cat) {
      return '<option value="' + esc(cat.id) + '"' + (cat.id === preselect ? " selected" : "") + ">" + esc(cat.name) + "</option>";
    }).join("");

    return '<div class="crumbs"><a href="#/">Forum</a><span class="sep">/</span><span>New thread</span></div>' +
    '<h1 class="page-title">Start a new thread</h1>' +
    '<p class="page-sub">Keep titles specific. Trip reports, measured numbers, and version details make a thread worth reading later.</p>' +
    '<form class="card" data-action="new-thread"><div class="card-body">' +
      '<div class="field">' +
        '<label for="thread-cat">Category</label>' +
        '<select id="thread-cat" name="cat">' + options + "</select>" +
      "</div>" +
      '<div class="field">' +
        '<label for="thread-title">Title</label>' +
        '<input type="text" id="thread-title" name="title" maxlength="120" placeholder="What is the thread about?" required />' +
        '<div class="help">Up to 120 characters.</div>' +
      "</div>" +
      '<div class="field">' +
        '<label for="thread-body">Opening post</label>' +
        '<textarea id="thread-body" name="body" placeholder="Give people the context, what you observed, and what you are asking." required></textarea>' +
        '<div class="help">You are posting as <strong>' + esc(handle || "a new member") + "</strong>." +
          (handle ? "" : " You will be asked to choose a handle when you submit.") + "</div>" +
      "</div>" +
      '<div class="form-actions">' +
        '<button class="btn btn-primary" type="submit">Publish thread</button>' +
        '<a class="btn btn-ghost" href="#/">Cancel</a>' +
      "</div>" +
    "</div></form>";
  }

  /* ---------------------------------------------------------- view: search */

  function viewSearch(query) {
    var q = (query || "").trim();

    if (!q) {
      return '<h1 class="page-title">Search</h1>' +
        '<p class="page-sub">Search thread titles, post bodies, and author handles.</p>' +
        '<div class="card"><div class="empty"><h3>Start typing</h3><p>Enter a term in the search box above and press Enter.</p></div></div>';
    }

    var needle = q.toLowerCase();

    var hits = state.threads.filter(function (thread) {
      if (thread.title.toLowerCase().indexOf(needle) !== -1) return true;
      if (thread.body.toLowerCase().indexOf(needle) !== -1) return true;
      if (thread.author.toLowerCase().indexOf(needle) !== -1) return true;
      return postsFor(thread.id).some(function (post) {
        return post.body.toLowerCase().indexOf(needle) !== -1 || post.author.toLowerCase().indexOf(needle) !== -1;
      });
    });

    return '<div class="crumbs"><a href="#/">Forum</a><span class="sep">/</span><span>Search</span></div>' +
      '<h1 class="page-title">Results for \u201c' + esc(q) + '\u201d</h1>' +
      '<p class="page-sub">' + hits.length + " matching thread" + (hits.length === 1 ? "" : "s") + ".</p>" +
      (hits.length
        ? threadListCard(sortedThreads(hits, "latest"))
        : '<div class="card"><div class="empty"><h3>No matches</h3><p>Try a shorter or more general term.</p><a class="btn" href="#/">Back to the forum</a></div></div>');
  }

  /* ------------------------------------------------------------ view: user */

  function viewUser(handle) {
    var name = String(handle || "");
    if (!name) return notFound("No member specified.");

    var theirThreads = state.threads.filter(function (t) { return t.author === name; });
    var theirPosts = state.posts.filter(function (p) { return p.author === name; });
    var isMe = name === myHandle();

    var html = '<div class="crumbs"><a href="#/">Forum</a><span class="sep">/</span><span>' + esc(name) + "</span></div>";

    html += '<div class="card" style="margin-bottom:18px"><div class="card-body" style="display:flex;gap:16px;align-items:center">' +
      avatarHtml(name, true) +
      "<div>" +
        '<h1 class="page-title" style="margin:0 0 4px;font-size:19px">' + esc(name) +
          (isMe ? ' <span class="badge">You</span>' : "") + "</h1>" +
        '<div class="meta">' +
          "<span>" + theirThreads.length + " threads</span>" +
          '<span class="sep">\u00b7</span>' +
          "<span>" + theirPosts.length + " replies</span>" +
        "</div>" +
      "</div>" +
    "</div></div>";

    if (theirThreads.length) {
      html += '<h2 style="font-size:16px;margin:0 0 10px">Threads started</h2>' +
        '<div style="margin-bottom:22px">' + threadListCard(sortedThreads(theirThreads, "latest")) + "</div>";
    }

    if (theirPosts.length) {
      var recent = theirPosts.slice().sort(function (a, b) { return b.createdAt - a.createdAt; }).slice(0, 8);
      html += '<h2 style="font-size:16px;margin:0 0 10px">Recent replies</h2>' +
        '<div class="card"><div class="thread-list">' + recent.map(function (post) {
          var thread = byId(state.threads, post.threadId);
          if (!thread) return "";
          return '<a class="thread-row" href="#/t/' + esc(thread.id) + '">' +
            avatarHtml(post.author) +
            '<div class="thread-main">' +
              '<span class="thread-title">' + esc(thread.title) + "</span>" +
              '<div class="thread-snippet">' + esc(truncate(post.body, 160)) + "</div>" +
              '<div class="meta"><span>' + timeAgo(post.createdAt) + "</span></div>" +
            "</div>" +
            '<div class="thread-side">' + post.votes + "<div>votes</div></div>" +
          "</a>";
        }).join("") + "</div></div>";
    }

    if (!theirThreads.length && !theirPosts.length) {
      html += '<div class="card"><div class="empty"><h3>Nothing yet</h3><p>This member has not posted anything.</p></div></div>';
    }

    return html;
  }

  /* ----------------------------------------------------------- view: about */

  function viewAbout() {
    return '<div class="crumbs"><a href="#/">Forum</a><span class="sep">/</span><span>About</span></div>' +
    '<h1 class="page-title">About this project</h1>' +
    '<p class="page-sub">A community forum for the Tesla Cybercab and the wider robotaxi rollout.</p>' +
    '<div class="card"><div class="card-body prose">' +
      "<h3>What it is</h3>" +
      "<p>A forum with categories, threads, replies, upvotes, search, and per-member profiles. It covers the rollout as it happens: which zones are live, how the cars actually behave, what a mile costs, and how the depot side works.</p>" +

      "<h3>How it is built</h3>" +
      "<ul>" +
        "<li>Plain HTML, CSS, and JavaScript. No framework, no bundler, no dependencies.</li>" +
        "<li>Hash-based routing, so it works from the filesystem and on static hosting with no rewrite rules.</li>" +
        "<li>Posts and replies persist in browser local storage. Nothing is sent anywhere.</li>" +
        "<li>All content is seeded demo data, written to make the interface feel real during development.</li>" +
      "</ul>" +

      "<h3>Honest limitations</h3>" +
      "<ul>" +
        "<li>There is no server, so there is no shared state. Two people on two machines see two separate forums.</li>" +
        "<li>Handles are self-declared and unverified. There is no real authentication and no password.</li>" +
        "<li>Anyone can edit local storage and change anything they see.</li>" +
        "<li>Deleting your browser data resets the forum to its seed state.</li>" +
      "</ul>" +

      "<h3>Where it would go next</h3>" +
      "<ul>" +
        "<li>Swap the storage layer for a real API so the forum becomes genuinely shared.</li>" +
        "<li>Real accounts, moderation tools, and rate limiting.</li>" +
        "<li>Server-side rendering so threads are indexable by search engines.</li>" +
        "<li>Per-category subscriptions and digest emails.</li>" +
      "</ul>" +

      "<h3>Disclaimer</h3>" +
      "<p>This is an independent, unaffiliated fan project. Cybercab, Robotaxi, and FSD are trademarks of Tesla, Inc. Every handle, thread, and reply in this build is invented demo content and does not represent the views of any real person.</p>" +
    "</div></div>";
  }

  /* ------------------------------------------------------------- sidebar */

  function renderSidebar() {
    var sidebar = document.getElementById("sidebar");
    if (!sidebar) return;

    var counts = {};
    state.threads.forEach(function (thread) {
      counts[thread.cat] = (counts[thread.cat] || 0) + 1;
    });

    var categories = window.SEED.categories.map(function (cat) {
      return '<a class="cat-item" href="#/c/' + esc(cat.id) + '">' +
        '<span class="swatch" style="background:' + esc(cat.color) + '"></span>' +
        "<span>" +
          '<span class="cat-item-name">' + esc(cat.name) + "</span><br />" +
          '<span class="cat-item-sub">' + esc(truncate(cat.blurb, 42)) + "</span>" +
        "</span>" +
        '<span class="count">' + (counts[cat.id] || 0) + "</span>" +
      "</a>";
    }).join("");

    var recent = sortedThreads(state.threads, "latest").slice(0, 5).map(function (thread) {
      return '<div class="mini-item">' +
        '<a class="t" href="#/t/' + esc(thread.id) + '">' + esc(truncate(thread.title, 58)) + "</a>" +
        '<span class="s">' + esc(thread.author) + " \u00b7 " + timeAgo(threadStats(thread).last) + "</span>" +
      "</div>";
    }).join("");

    sidebar.innerHTML =
      '<div class="card"><div class="card-head"><h3 class="side-title">Categories</h3></div>' +
        '<div class="cat-list">' + categories + "</div></div>" +
      '<div class="card"><div class="card-head"><h3 class="side-title">Latest activity</h3></div>' +
        '<div class="mini-list">' + recent + "</div></div>" +
      '<div class="card"><div class="card-head"><h3 class="side-title">About this build</h3></div>' +
        '<div class="card-body prose" style="font-size:13.5px">' +
          "<p>Static site, zero dependencies, no backend. Threads live in your browser only.</p>" +
          '<p style="margin-bottom:0"><a href="#/about">Read more \u2192</a></p>' +
        "</div></div>";
  }

  /* --------------------------------------------------------------- catbar */

  function renderCatbar(segments) {
    var bar = document.getElementById("catbar");
    if (!bar) return;

    var active = segments[0] === "c" ? segments[1] : null;

    var html = '<a class="catpill' + (segments.length === 0 ? " is-active" : "") + '" href="#/">All</a>';

    html += window.SEED.categories.map(function (cat) {
      return '<a class="catpill' + (active === cat.id ? " is-active" : "") + '" href="#/c/' + esc(cat.id) + '">' +
        '<span class="swatch" style="background:' + esc(cat.color) + '"></span>' + esc(cat.name) +
      "</a>";
    }).join("");

    bar.innerHTML = html;
  }

  /* ---------------------------------------------------------------- toast */

  var toastEl = null;
  var toastTimer = null;

  function toast(message) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "toast";
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.classList.add("is-on");
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { toastEl.classList.remove("is-on"); }, 2400);
  }

  /* --------------------------------------------------------------- router */

  function render() {
    var route = parseHash();
    var segments = route.segments;
    var view = document.getElementById("view");
    if (!view) return;

    var html = "";
    var title = "Cybercab Forum";

    if (segments.length === 0) {
      html = viewHome();
      title = "Cybercab Forum \u2014 Tesla Robotaxi Community";
    } else if (segments[0] === "c" && segments[1]) {
      html = viewCategory(segments[1]);
    } else if (segments[0] === "t" && segments[1]) {
      html = viewThread(segments[1]);
      var thread = byId(state.threads, segments[1]);
      if (thread) title = thread.title + " \u2014 Cybercab Forum";
    } else if (segments[0] === "new") {
      html = viewNewThread();
      title = "New thread \u2014 Cybercab Forum";
    } else if (segments[0] === "search") {
      var q = param("q");
      html = viewSearch(q);
      var input = document.getElementById("search-input");
      if (input) input.value = q;
      title = "Search \u2014 Cybercab Forum";
    } else if (segments[0] === "u" && segments[1]) {
      html = viewUser(decodeURIComponent(segments[1]));
    } else if (segments[0] === "about") {
      html = viewAbout();
      title = "About \u2014 Cybercab Forum";
    } else {
      html = notFound("That page does not exist.");
    }

    view.innerHTML = html;
    document.title = title;
    renderCatbar(segments);
    renderSidebar();

    if (route.path !== lastPath) {
      lastPath = route.path;
      window.scrollTo(0, 0);
    }
  }

  /* --------------------------------------------------------------- actions */

  function handleVote(kind, id) {
    var key = kind + ":" + id;
    var target = kind === "t" ? byId(state.threads, id) : byId(state.posts, id);
    if (!target) return;

    if (state.myVotes[key]) {
      target.votes = Math.max(0, target.votes - 1);
      delete state.myVotes[key];
    } else {
      target.votes += 1;
      state.myVotes[key] = 1;
    }
    saveState();

    var action = kind === "t" ? "vote-thread" : "vote-post";
    var button = document.querySelector('[data-action="' + action + '"][data-id="' + id + '"]');
    if (button) {
      var count = button.querySelector(".vote-count");
      if (count) count.textContent = target.votes;
      if (state.myVotes[key]) button.classList.add("is-voted");
      else button.classList.remove("is-voted");
    }
  }

  function deletePost(id) {
    var post = byId(state.posts, id);
    if (!post) return;

    if (post.author !== myHandle()) {
      toast("You can only delete your own replies.");
      return;
    }
    if (!window.confirm("Delete this reply?")) return;

    state.posts = state.posts.filter(function (p) { return p.id !== id; });
    saveState();
    toast("Reply deleted.");
    render();
  }

  function submitReply(form) {
    var threadId = form.getAttribute("data-thread");
    var field = form.querySelector('textarea[name="body"]');
    var body = field ? field.value.trim() : "";

    if (!body) { toast("Write something first."); return; }

    var handle = ensureHandle(false);
    if (!handle) { toast("Choose a handle before posting."); return; }

    state.posts.push({
      id: uid("post"),
      threadId: threadId,
      author: handle,
      body: body,
      createdAt: Date.now(),
      votes: 0
    });
    saveState();
    toast("Reply posted.");
    render();
  }

  function submitThread(form) {
    var titleField = form.querySelector('input[name="title"]');
    var bodyField = form.querySelector('textarea[name="body"]');
    var catField = form.querySelector('select[name="cat"]');

    var title = titleField ? titleField.value.trim() : "";
    var body = bodyField ? bodyField.value.trim() : "";
    var cat = catField ? catField.value : "";

    if (title.length < 6) { toast("Give the thread a longer title."); titleField && titleField.focus(); return; }
    if (body.length < 10) { toast("Add a little more detail to the opening post."); bodyField && bodyField.focus(); return; }

    var handle = ensureHandle(false);
    if (!handle) { toast("Choose a handle before posting."); return; }

    var thread = {
      id: uid("t"),
      cat: cat,
      title: title,
      body: body,
      author: handle,
      createdAt: Date.now(),
      pinned: false,
      views: 0,
      votes: 0
    };

    state.threads.push(thread);
    saveState();
    toast("Thread published.");
    go("#/t/" + thread.id);
  }

  function resetDemo() {
    if (!window.confirm("Reset the forum to its original seed content? Anything you posted will be lost.")) return;
    storeRemove(STORAGE_KEY);
    state = loadState();
    viewedThisSession = {};
    ui.sort = "latest";
    toast("Demo data reset.");
    go("#/");
    render();
  }

  /* ---------------------------------------------------------------- events */

  document.addEventListener("click", function (event) {
    var target = event.target;
    var el = target && target.closest ? target.closest("[data-action]") : null;
    if (!el) return;

    var action = el.getAttribute("data-action");

    if (action === "sort") {
      ui.sort = el.getAttribute("data-value") || "latest";
      render();
    } else if (action === "vote-thread") {
      handleVote("t", el.getAttribute("data-id"));
    } else if (action === "vote-post") {
      handleVote("p", el.getAttribute("data-id"));
    } else if (action === "delete-post") {
      deletePost(el.getAttribute("data-id"));
    }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    var action = form.getAttribute("data-action");

    if (form.id === "search-form") {
      event.preventDefault();
      var q = document.getElementById("search-input").value.trim();
      go("#/search?q=" + encodeURIComponent(q));
      return;
    }

    if (action === "reply") {
      event.preventDefault();
      submitReply(form);
    } else if (action === "new-thread") {
      event.preventDefault();
      submitThread(form);
    }
  });

  /* ------------------------------------------------------------------ init */

  function init() {
    state = loadState();
    refreshIdentity();

    var statusEl = document.getElementById("storage-status");
    if (statusEl) {
      statusEl.textContent = storageWorks ? "saved in this browser" : "in-memory only (storage blocked)";
    }

    var identityBtn = document.getElementById("identity-btn");
    if (identityBtn) {
      identityBtn.addEventListener("click", function () {
        ensureHandle(true);
        render();
      });
    }

    var resetBtn = document.getElementById("reset-btn");
    if (resetBtn) resetBtn.addEventListener("click", resetDemo);

    document.addEventListener("keydown", function (event) {
      var tag = document.activeElement ? document.activeElement.tagName : "";
      if (event.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        event.preventDefault();
        var input = document.getElementById("search-input");
        if (input) input.focus();
      }
    });

    window.addEventListener("hashchange", render);
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
