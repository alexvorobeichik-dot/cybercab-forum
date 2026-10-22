"""Integration tests for the Cybercab Forum.

Runs the real HTTP server against a temporary database and exercises the
paths that matter: registration, sign-in and sign-out, publishing, replies,
output escaping, CSRF rejection, session cookie flags, rate limiting, and
moderator locking and deletion.

Run with:
    python -m unittest test_forum.py -v
"""
import http.client
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.parse
import xml.etree.ElementTree
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The database path and the registration gate are read when the application is
# imported, so the environment has to be prepared first.
TEST_DIR = tempfile.mkdtemp(prefix='cybercab-forum-test-')
os.environ['FORUM_DB'] = os.path.join(TEST_DIR, 'forum.db')
os.environ['FORUM_REGISTRATION_OPEN'] = '1'
os.environ['FORUM_SECURE'] = '0'
os.environ['HOST'] = '127.0.0.1'

import server  # noqa: E402  (must follow the environment setup above)

PASSWORD = 'correct-horse-battery'
WRONG_PASSWORD = 'definitely-not-it'


class Client:
    """Minimal HTTP client that keeps session cookies and never follows redirects."""

    def __init__(self, port):
        self.port = port
        self.cookies = {}

    def fetch(self, method, path, data=None, headers=None):
        """Return (status, headers, raw bytes). Use this for binary assets."""
        body = urllib.parse.urlencode(data) if data is not None else None
        outgoing = dict(headers or {})
        if body is not None:
            outgoing['Content-Type'] = 'application/x-www-form-urlencoded'
        if self.cookies:
            outgoing['Cookie'] = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=outgoing)
            response = connection.getresponse()
            payload = response.read()
            self._remember(response.headers)
            return response.status, response.headers, payload
        finally:
            connection.close()

    def request(self, method, path, data=None, headers=None):
        status, response_headers, payload = self.fetch(method, path, data, headers)
        return status, response_headers, payload.decode('utf-8', 'replace')

    def _remember(self, headers):
        for raw in headers.get_all('Set-Cookie') or []:
            parts = [part.strip() for part in raw.split(';')]
            name, _, value = parts[0].partition('=')
            if any(part.lower() == 'max-age=0' for part in parts[1:]):
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = value

    def get(self, path, headers=None):
        return self.request('GET', path, headers=headers)

    def post(self, path, data=None, headers=None):
        return self.request('POST', path, data=data, headers=headers)

    def form_token(self, path):
        """Fetch a page and return its CSRF token, or None."""
        _, _, body = self.get(path)
        match = re.search(r'name="csrf" value="([^"]+)"', body)
        return match.group(1) if match else None


class ForumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init()
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.httpd.daemon_threads = True
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def setUp(self):
        # Rate limiting is deliberately process-wide state; clear it between
        # tests so one test's flood cannot fail the next one.
        server.RATE.clear()
        server.REGISTRATION_OPEN = True

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    counter = 0

    def unique(self, prefix):
        ForumTests.counter += 1
        return f'{prefix}{ForumTests.counter}'

    def client(self):
        return Client(self.port)

    def db(self):
        connection = sqlite3.connect(os.environ['FORUM_DB'])
        connection.row_factory = sqlite3.Row
        return connection

    def query(self, sql, args=()):
        connection = self.db()
        try:
            return connection.execute(sql, args).fetchall()
        finally:
            connection.close()

    def scalar(self, sql, args=()):
        return self.query(sql, args)[0][0]

    def execute(self, sql, args=()):
        connection = self.db()
        try:
            connection.execute(sql, args)
            connection.commit()
        finally:
            connection.close()

    def register(self, client, name, password=PASSWORD):
        return client.post('/register', {'name': name, 'password': password})

    def make_user(self, prefix):
        client = self.client()
        name = self.unique(prefix)
        status, _, _ = self.register(client, name)
        self.assertEqual(status, 303, f'could not register {name}')
        return client, name

    def make_topic(self, client, title=None, category='Technology', body='Body text.'):
        token = client.form_token('/new')
        self.assertIsNotNone(token, 'no CSRF token on /new')
        status, headers, _ = client.post('/new', {
            'csrf': token, 'title': title or self.unique('Topic '),
            'category': category, 'body': body})
        self.assertEqual(status, 303, 'topic creation did not redirect')
        return headers['Location']

    def promote(self, name):
        self.execute('UPDATE users SET admin=1 WHERE name=?', (name,))

    # ------------------------------------------------------------------
    # basics
    # ------------------------------------------------------------------
    def test_healthz_reports_ok(self):
        status, _, body = self.client().get('/healthz')
        self.assertEqual(status, 200)
        self.assertEqual(body, 'ok')

    def test_homepage_and_guidelines_render(self):
        client = self.client()
        status, _, body = client.get('/')
        self.assertEqual(status, 200)
        self.assertIn('Cybercab Forum', body)
        status, _, body = client.get('/guidelines')
        self.assertEqual(status, 200)
        self.assertIn('Guidelines', body)

    def test_security_headers_are_sent(self):
        _, headers, _ = self.client().get('/')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])

    def test_robots_txt_is_served_and_points_at_the_sitemap(self):
        status, headers, body = self.client().get('/robots.txt')
        self.assertEqual(status, 200)
        self.assertIn('text/plain', headers['Content-Type'])
        self.assertIn('Allow: /', body)
        self.assertIn('Disallow: /login', body)
        self.assertIn(f'Sitemap: {server.SITE_URL}/sitemap.xml', body)

    def test_sitemap_lists_topics_and_is_well_formed_xml(self):
        client, _ = self.make_user('sitemap')
        location = self.make_topic(client, title='A topic the sitemap should list')
        status, headers, body = self.client().get('/sitemap.xml')
        self.assertEqual(status, 200)
        self.assertIn('xml', headers['Content-Type'])
        self.assertIn(f'{server.SITE_URL}/guidelines', body)
        self.assertIn(f'{server.SITE_URL}{location}', body)
        self.assertEqual(body.count('<url>'), body.count('</url>'))
        xml.etree.ElementTree.fromstring(body)  # must parse

    def test_pages_carry_canonical_and_open_graph_tags(self):
        _, _, body = self.client().get('/')
        self.assertIn(f'<link rel="canonical" href="{server.SITE_URL}/">', body)
        self.assertIn('<meta property="og:title" content="Community · Cybercab Forum">', body)
        self.assertIn(f'<meta property="og:image" content="{server.SITE_URL}/static/og-card.png">', body)
        self.assertIn('name="twitter:card"', body)

    def test_share_card_is_actually_served(self):
        # The Open Graph tags point at this file, so a missing or renamed asset
        # would leave every shared link with a broken preview.
        status, headers, payload = self.client().fetch('GET', '/static/og-card.png')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertTrue(payload.startswith(b'\x89PNG\r\n'), 'not a PNG')
        self.assertGreater(len(payload), 10000, 'suspiciously small share card')

    # ------------------------------------------------------------------
    # operator bootstrap and self-service account changes
    # ------------------------------------------------------------------
    def test_account_page_requires_a_session(self):
        status, headers, _ = self.client().get('/account')
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/login')

    def test_member_can_change_their_own_password(self):
        client, name = self.make_user('changer')
        token = client.form_token('/account')
        self.assertIsNotNone(token, 'no CSRF token on the account page')
        status, _, _ = client.post('/account', {'csrf': token, 'current': PASSWORD,
                                                'password': 'a-brand-new-password',
                                                'confirm': 'a-brand-new-password'})
        self.assertEqual(status, 303)
        self.assertEqual(
            self.client().post('/login', {'name': name, 'password': PASSWORD})[0], 401,
            'the old password must stop working')
        self.assertEqual(
            self.client().post('/login', {'name': name,
                                          'password': 'a-brand-new-password'})[0], 303)

    def test_password_change_requires_the_current_password(self):
        client, name = self.make_user('wrongcurrent')
        token = client.form_token('/account')
        status, _, body = client.post('/account', {'csrf': token, 'current': WRONG_PASSWORD,
                                                   'password': 'another-new-password',
                                                   'confirm': 'another-new-password'})
        self.assertEqual(status, 403)
        self.assertIn('current password is not correct', body)
        self.assertEqual(
            self.client().post('/login', {'name': name, 'password': PASSWORD})[0], 303,
            'the password must be unchanged')

    def test_password_change_rejects_a_mismatched_confirmation(self):
        client, _ = self.make_user('mismatch')
        token = client.form_token('/account')
        status, _, body = client.post('/account', {'csrf': token, 'current': PASSWORD,
                                                   'password': 'one-new-password-here',
                                                   'confirm': 'a-different-new-one-here'})
        self.assertEqual(status, 400)
        self.assertIn('did not match', body)

    def test_password_change_rejects_a_short_new_password(self):
        client, _ = self.make_user('shortnew')
        token = client.form_token('/account')
        status, _, body = client.post('/account', {'csrf': token, 'current': PASSWORD,
                                                   'password': 'tooshort',
                                                   'confirm': 'tooshort'})
        self.assertEqual(status, 400)
        self.assertIn('12-128 characters', body)

    def test_password_change_requires_csrf(self):
        client, _ = self.make_user('pwcsrf')
        status, _, _ = client.post('/account', {'csrf': 'forged', 'current': PASSWORD,
                                                'password': 'brand-new-password-x',
                                                'confirm': 'brand-new-password-x'})
        self.assertEqual(status, 403)

    def test_password_change_signs_out_other_devices_only(self):
        first, name = self.make_user('twodevices')
        second = self.client()
        self.assertEqual(
            second.post('/login', {'name': name, 'password': PASSWORD})[0], 303)
        token = first.form_token('/account')
        status, _, _ = first.post('/account', {'csrf': token, 'current': PASSWORD,
                                               'password': 'changed-on-one-device',
                                               'confirm': 'changed-on-one-device'})
        self.assertEqual(status, 303)
        self.assertEqual(second.get('/new')[0], 303, 'the other device should be signed out')
        self.assertEqual(first.get('/new')[0], 200, 'this device should stay signed in')

    def test_bootstrap_admin_promotes_when_no_moderator_exists(self):
        _, name = self.make_user('bootstrapped')
        self.execute('UPDATE users SET admin=0')
        os.environ['FORUM_BOOTSTRAP_ADMIN'] = name
        try:
            server.bootstrap_admin()
        finally:
            del os.environ['FORUM_BOOTSTRAP_ADMIN']
        self.assertEqual(
            self.scalar('SELECT admin FROM users WHERE name=?', (name,)), 1,
            'the named account should be promoted when nobody can moderate')
        self.execute('UPDATE users SET admin=0')

    def test_bootstrap_admin_leaves_an_existing_moderator_alone(self):
        _, guardian = self.make_user('guardian')
        self.promote(guardian)
        _, candidate = self.make_user('candidate')
        os.environ['FORUM_BOOTSTRAP_ADMIN'] = candidate
        try:
            server.bootstrap_admin()
        finally:
            del os.environ['FORUM_BOOTSTRAP_ADMIN']
        self.assertEqual(
            self.scalar('SELECT admin FROM users WHERE name=?', (candidate,)), 0,
            'must not promote anyone while a moderator exists')

    def test_bootstrap_admin_ignores_an_account_that_does_not_exist(self):
        self.execute('UPDATE users SET admin=0')
        os.environ['FORUM_BOOTSTRAP_ADMIN'] = 'nobody-at-all'
        try:
            server.bootstrap_admin()   # must not raise
        finally:
            del os.environ['FORUM_BOOTSTRAP_ADMIN']
        self.assertEqual(self.scalar('SELECT count(*) FROM users WHERE admin=1'), 0)

    # ------------------------------------------------------------------
    # editing your own posts
    # ------------------------------------------------------------------
    def test_author_can_edit_their_own_topic(self):
        client, name = self.make_user('editor')
        location = self.make_topic(client, title='Original title', body='Original body.')
        topic_id = location.rsplit('/', 1)[1]

        status, _, form = client.get(f'/edit/topic/{topic_id}')
        self.assertEqual(status, 200)
        self.assertIn('value="Original title"', form, 'the form must be pre-filled')
        self.assertIn('Original body.', form)

        token = client.form_token(f'/edit/topic/{topic_id}')
        status, headers, _ = client.post(f'/edit/topic/{topic_id}', {
            'csrf': token, 'title': 'Revised title',
            'category': 'Technology', 'body': 'Revised body.'})
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], location)

        _, _, page = client.get(location)
        self.assertIn('Revised title', page)
        self.assertIn('Revised body.', page)
        self.assertNotIn('Original body.', page)
        self.assertIn(name, page, 'editing must not change the author')
        self.assertIn('edited', page, 'an edit must be marked')
        self.assertIsNotNone(
            self.scalar('SELECT edited FROM topics WHERE id=?', (int(topic_id),)))

    def test_only_the_author_can_edit_a_topic(self):
        author, _ = self.make_user('owner')
        location = self.make_topic(author, title='Owned topic')
        topic_id = location.rsplit('/', 1)[1]

        outsider, _ = self.make_user('meddler')
        self.assertEqual(outsider.get(f'/edit/topic/{topic_id}')[0], 403,
                         'the edit form must be refused')
        # A valid CSRF token for their own session, so the request reaches the
        # ownership check rather than being stopped by CSRF first.
        token = outsider.form_token('/new')
        status, _, _ = outsider.post(f'/edit/topic/{topic_id}', {
            'csrf': token, 'title': 'Hijacked',
            'category': 'Technology', 'body': 'Hijacked.'})
        self.assertEqual(status, 403, 'the write must be refused too')
        self.assertIn('Owned topic', self.client().get(location)[2], 'unchanged')

    def test_editing_requires_a_session_and_a_csrf_token(self):
        client, _ = self.make_user('guardedit')
        location = self.make_topic(client)
        topic_id = location.rsplit('/', 1)[1]
        self.assertEqual(self.client().get(f'/edit/topic/{topic_id}')[0], 303)
        self.assertEqual(self.client().post(f'/edit/topic/{topic_id}', {
            'csrf': 'x', 'title': 'y', 'category': 'Technology', 'body': 'z'})[0], 401)
        status, _, _ = client.post(f'/edit/topic/{topic_id}', {
            'csrf': 'forged', 'title': 'y', 'category': 'Technology', 'body': 'z'})
        self.assertEqual(status, 403)

    def test_author_can_edit_their_own_reply(self):
        client, _ = self.make_user('replyedit')
        location = self.make_topic(client)
        topic_id = location.rsplit('/', 1)[1]
        token = client.form_token(location)
        client.post(f'/reply/{topic_id}', {'csrf': token, 'body': 'First version.'})
        reply_id = self.scalar('SELECT id FROM replies WHERE topic_id=?', (int(topic_id),))

        status, _, form = client.get(f'/edit/reply/{reply_id}')
        self.assertEqual(status, 200)
        self.assertIn('First version.', form)

        token = client.form_token(f'/edit/reply/{reply_id}')
        status, _, _ = client.post(f'/edit/reply/{reply_id}',
                                   {'csrf': token, 'body': 'Second version.'})
        self.assertEqual(status, 303)
        _, _, page = client.get(location)
        self.assertIn('Second version.', page)
        self.assertNotIn('First version.', page)

    def test_only_the_author_can_edit_a_reply(self):
        author, _ = self.make_user('replyowner')
        location = self.make_topic(author)
        topic_id = location.rsplit('/', 1)[1]
        token = author.form_token(location)
        author.post(f'/reply/{topic_id}', {'csrf': token, 'body': 'The original reply.'})
        reply_id = self.scalar('SELECT id FROM replies WHERE topic_id=?', (int(topic_id),))

        outsider, _ = self.make_user('replymeddler')
        self.assertEqual(outsider.get(f'/edit/reply/{reply_id}')[0], 403)
        token = outsider.form_token('/new')
        self.assertEqual(outsider.post(f'/edit/reply/{reply_id}',
                                       {'csrf': token, 'body': 'Rewritten.'})[0], 403)
        self.assertIn('The original reply.', self.client().get(location)[2])

    def test_editing_rejects_invalid_input(self):
        client, _ = self.make_user('badedit')
        location = self.make_topic(client)
        topic_id = location.rsplit('/', 1)[1]
        token = client.form_token(f'/edit/topic/{topic_id}')
        self.assertEqual(client.post(f'/edit/topic/{topic_id}', {
            'csrf': token, 'title': 'x' * 161,
            'category': 'Technology', 'body': 'fine'})[0], 400)
        token = client.form_token(f'/edit/topic/{topic_id}')
        self.assertEqual(client.post(f'/edit/topic/{topic_id}', {
            'csrf': token, 'title': 'fine',
            'category': 'Not A Category', 'body': 'fine'})[0], 400)

    def test_editing_an_unknown_post_is_a_404(self):
        client, _ = self.make_user('missingedit')
        for path in ('/edit/topic/999999', '/edit/reply/999999',
                     '/edit/bogus/1', '/edit/topic/not-a-number'):
            with self.subTest(path=path):
                self.assertEqual(client.get(path)[0], 404)

    def test_migration_adds_the_edited_column_to_an_older_database(self):
        # Production already had data when editing was added, and its tables
        # have no `edited` column. If the migration fails, init() raises and the
        # service refuses to start, so this checks the real upgrade path.
        legacy = os.path.join(TEST_DIR, 'legacy.db')
        con = sqlite3.connect(legacy)
        con.executescript(
            'CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,'
            'password TEXT NOT NULL,admin INTEGER DEFAULT 0);'
            'CREATE TABLE topics(id INTEGER PRIMARY KEY,title TEXT,body TEXT,category TEXT,'
            'user_id INTEGER,created TEXT DEFAULT CURRENT_TIMESTAMP,locked INTEGER DEFAULT 0);'
            'CREATE TABLE replies(id INTEGER PRIMARY KEY,topic_id INTEGER,user_id INTEGER,'
            'body TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);')
        con.execute('INSERT INTO topics(title,body,category,user_id) VALUES(?,?,?,?)',
                    ('Pre-existing topic', 'Body.', 'Technology', 1))
        con.commit()
        con.close()

        original = server.DB
        server.DB = legacy
        try:
            server.init()
            con = sqlite3.connect(legacy)
            topics = {r[1] for r in con.execute('PRAGMA table_info(topics)')}
            replies = {r[1] for r in con.execute('PRAGMA table_info(replies)')}
            surviving = con.execute('SELECT title FROM topics').fetchone()[0]
            con.close()
        finally:
            server.DB = original

        self.assertIn('edited', topics, 'topics must gain the column')
        self.assertIn('edited', replies, 'replies must gain the column')
        self.assertEqual(surviving, 'Pre-existing topic', 'existing rows must survive')

    def test_topic_pages_use_article_metadata(self):
        client, _ = self.make_user('article')
        location = self.make_topic(
            client, title='Metadata topic',
            body='The quick brown fox jumps over the lazy dog.')
        _, _, body = self.client().get(location)
        self.assertIn(f'<link rel="canonical" href="{server.SITE_URL}{location}">', body)
        self.assertIn('<meta property="og:type" content="article">', body)
        self.assertIn('The quick brown fox jumps over the lazy dog.', body)

    # ------------------------------------------------------------------
    # feeds
    # ------------------------------------------------------------------
    def test_rfc822_format(self):
        # Feed readers silently drop items whose pubDate they cannot parse, and
        # strftime would emit the local month names on a non-English server.
        self.assertEqual(server.rfc822('2026-10-18 04:51:26'),
                         'Sun, 18 Oct 2026 04:51:26 +0000')
        self.assertEqual(server.rfc822('2026-01-01 00:00:00'),
                         'Thu, 01 Jan 2026 00:00:00 +0000')
        self.assertEqual(server.rfc822('not a date'), '')

    def test_site_feed_lists_topics_and_replies(self):
        client, _ = self.make_user('feeder')
        location = self.make_topic(client, title='A topic for the feed')
        topic_id = location.rsplit('/', 1)[1]
        token = client.form_token(location)
        client.post(f'/reply/{topic_id}', {'csrf': token, 'body': 'A reply for the feed.'})

        status, headers, body = self.client().get('/feed.xml')
        self.assertEqual(status, 200)
        self.assertIn('rss+xml', headers['Content-Type'])
        root = xml.etree.ElementTree.fromstring(body)   # must parse
        self.assertEqual(root.tag, 'rss')
        titles = [e.text for e in root.iter('title')]
        self.assertIn('Cybercab Forum', titles)
        self.assertTrue(any('A topic for the feed' in t for t in titles), titles)
        self.assertTrue(any(t.startswith('Re: ') for t in titles), titles)
        for published in root.iter('pubDate'):
            self.assertRegex(
                published.text,
                r'^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} \+0000$')

    def test_topic_feed_contains_that_thread_only(self):
        client, _ = self.make_user('topicfeed')
        location = self.make_topic(client, title='Thread with its own feed')
        topic_id = location.rsplit('/', 1)[1]
        token = client.form_token(location)
        client.post(f'/reply/{topic_id}', {'csrf': token, 'body': 'Reply inside the thread.'})

        status, headers, body = self.client().get(f'/topic/{topic_id}/feed.xml')
        self.assertEqual(status, 200)
        self.assertIn('rss+xml', headers['Content-Type'])
        root = xml.etree.ElementTree.fromstring(body)
        self.assertEqual(len(list(root.iter('item'))), 2, 'the topic plus its one reply')

    def test_topic_feed_for_an_unknown_topic_is_404(self):
        self.assertEqual(self.client().get('/topic/999999/feed.xml')[0], 404)
        self.assertEqual(self.client().get('/topic/nonsense/feed.xml')[0], 404)

    def test_feeds_are_discoverable_from_the_pages(self):
        client, _ = self.make_user('discover')
        location = self.make_topic(client)
        _, _, home = self.client().get('/')
        self.assertIn(f'href="{server.SITE_URL}/feed.xml"', home)
        self.assertIn('application/rss+xml', home)
        _, _, topic = self.client().get(location)
        self.assertIn(f'href="{server.SITE_URL}{location}/feed.xml"', topic)

    def test_replies_have_anchors_so_feed_links_resolve(self):
        client, _ = self.make_user('anchors')
        location = self.make_topic(client)
        topic_id = location.rsplit('/', 1)[1]
        token = client.form_token(location)
        client.post(f'/reply/{topic_id}', {'csrf': token, 'body': 'Anchor me.'})
        reply_id = self.scalar('SELECT id FROM replies WHERE topic_id=?', (int(topic_id),))
        _, _, page = self.client().get(location)
        self.assertIn(f'id="reply-{reply_id}"', page)
        _, _, feed = self.client().get('/feed.xml')
        self.assertIn(f'#reply-{reply_id}', feed, 'the feed must link to the anchor')

    # ------------------------------------------------------------------
    # reference pages
    # ------------------------------------------------------------------
    def test_service_areas_page_lists_every_tesla_market(self):
        status, _, body = self.client().get('/service-areas')
        self.assertEqual(status, 200)
        for market in ('Austin', 'Dallas', 'Houston', 'Miami', 'Orlando', 'Tampa', 'Bay Area'):
            with self.subTest(market=market):
                self.assertIn(market, body)
        self.assertIn('Live since 3 Sep 2026', body, 'Austin is the only Cybercab market')
        self.assertIn('driverlessmap.com', body,
                      'the page must point at the version that is kept current')
        # The sourced tables moved to driverlessmap.com. If they creep back in
        # here there are two copies to maintain, which is the drift this avoided.
        self.assertNotIn('Las Vegas', body)
        self.assertNotIn('Approved or preparing', body)

    def test_service_areas_page_charts_the_registration_data(self):
        _, _, body = self.client().get('/service-areas')
        self.assertIn('<svg', body)
        self.assertIn('class="chart"', body)
        self.assertIn('role="img"', body, 'the chart needs an accessible name')
        for label, value in server.CYBERCAB_REGISTRATIONS:
            with self.subTest(point=label):
                self.assertIn(label, body)
                self.assertIn(f'>{value}<', body)

    def test_regulations_page_points_at_the_sourced_version(self):
        status, _, body = self.client().get('/regulations')
        self.assertEqual(status, 200)
        for place in ('United States, federal', 'Texas', 'California',
                      'Nevada and Arizona', 'Florida'):
            with self.subTest(place=place):
                self.assertIn(place, body)
        self.assertIn('AQ26002', body, 'the audit query identifier is the point of the page')
        self.assertIn('driverlessmap.com/regulations', body)

    def test_reference_pages_are_metadata_complete_and_discoverable(self):
        for path in ('/service-areas', '/regulations'):
            with self.subTest(path=path):
                _, _, body = self.client().get(path)
                self.assertIn(f'<link rel="canonical" href="{server.SITE_URL}{path}">', body)
                self.assertIn('<meta property="og:type" content="website">', body)
        _, _, page = self.client().get('/')
        self.assertIn('href="/service-areas"', page)
        self.assertIn('href="/regulations"', page)
        _, _, sitemap = self.client().get('/sitemap.xml')
        self.assertIn(server.SITE_URL + '/service-areas', sitemap)
        self.assertIn(server.SITE_URL + '/regulations', sitemap)

    def test_remaining_reference_rows_still_carry_a_source(self):
        # The sourced tables for other operators moved to driverlessmap.com. What
        # is left here is Tesla's own market list, and it still has to be
        # traceable to a named source even though the page no longer prints them.
        for row in server.SERVICE_AREAS:
            with self.subTest(row=row['city']):
                self.assertTrue(row.get('source', '').startswith('https://'),
                                'every row needs a source URL')
                self.assertTrue(row.get('source_name'), 'and a named source')

    def test_unknown_routes_return_404(self):
        client = self.client()
        for path in ('/nope', '/topic/999999', '/topic/not-a-number', '/../etc/passwd'):
            with self.subTest(path=path):
                status, _, _ = client.get(path)
                self.assertEqual(status, 404)

    def test_oversized_request_is_rejected(self):
        status, _, _ = self.client().request(
            'POST', '/login', headers={'Content-Length': '999999'})
        self.assertEqual(status, 413)

    # ------------------------------------------------------------------
    # registration and sessions
    # ------------------------------------------------------------------
    def test_registration_can_be_closed(self):
        server.REGISTRATION_OPEN = False
        status, _, body = self.client().get('/register')
        self.assertEqual(status, 403)
        self.assertIn('not open yet', body)
        status, _, _ = self.register(self.client(), self.unique('closed'))
        self.assertEqual(status, 403)

    def test_register_then_sign_in_and_out(self):
        client = self.client()
        name = self.unique('alice')
        status, headers, _ = self.register(client, name)
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/')
        self.assertIn('session', client.cookies)

        _, _, home = client.get('/')
        self.assertIn(name, home)

        status, _, _ = client.post('/logout', {'csrf': client.form_token('/')})
        self.assertEqual(status, 303)
        self.assertNotIn('session', client.cookies)

        status, headers, _ = client.get('/new')
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/login')

    def test_session_cookie_is_httponly_samesite_and_secure_when_configured(self):
        client = self.client()
        _, headers, _ = self.register(client, self.unique('cookie'))
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)
        self.assertNotIn('Secure', cookie, 'Secure must be off while FORUM_SECURE != 1')

        os.environ['FORUM_SECURE'] = '1'
        try:
            _, headers, _ = self.register(self.client(), self.unique('cookie'))
            self.assertIn('Secure', headers['Set-Cookie'])
        finally:
            os.environ['FORUM_SECURE'] = '0'

    def test_sign_in_with_wrong_credentials_fails(self):
        client, name = self.make_user('signin')
        status, _, body = self.client().post(
            '/login', {'name': name, 'password': WRONG_PASSWORD})
        self.assertEqual(status, 401)
        self.assertIn('Invalid username or password', body)
        status, _, _ = self.sign_in_ok(self.client(), name)
        self.assertEqual(status, 303)

    def sign_in_ok(self, client, name, password=PASSWORD):
        return client.post('/login', {'name': name, 'password': password})

    def test_unknown_user_and_wrong_password_are_indistinguishable(self):
        _, name = self.make_user('known')
        wrong_for_known = self.client().post(
            '/login', {'name': name, 'password': WRONG_PASSWORD})
        unknown = self.client().post(
            '/login', {'name': self.unique('ghost'), 'password': WRONG_PASSWORD})
        self.assertEqual(wrong_for_known[0], unknown[0])
        self.assertEqual(wrong_for_known[2], unknown[2])

    def test_password_is_stored_as_a_salted_scrypt_hash(self):
        client = self.client()
        name = self.unique('hashed')
        self.register(client, name)
        stored = self.scalar('SELECT password FROM users WHERE name=?', (name,))
        self.assertNotIn(PASSWORD, stored)
        salt, _, digest = stored.partition(':')
        self.assertEqual(len(salt), 32, 'expected a 16-byte hex salt')
        self.assertEqual(len(digest), 128, 'expected a 64-byte scrypt digest')

    def test_admin_is_never_granted_automatically(self):
        # /guidelines states moderator access is assigned explicitly by the
        # operator, never to the first registrant. Registering must not confer it.
        client = self.client()
        name = self.unique('newcomer')
        self.register(client, name)
        self.assertEqual(self.scalar('SELECT admin FROM users WHERE name=?', (name,)), 0)

    def test_duplicate_username_is_rejected(self):
        name = self.unique('dupe')
        self.register(self.client(), name)
        status, _, body = self.register(self.client(), name)
        self.assertEqual(status, 400)
        self.assertIn('already registered', body)

    def test_username_and_password_validation(self):
        client = self.client()
        for bad_name in ('ab', 'has space', 'has-dash', 'a' * 31, 'caf\u00e9'):
            with self.subTest(name=bad_name):
                status, _, _ = client.post('/register', {'name': bad_name, 'password': PASSWORD})
                self.assertEqual(status, 400)
        for bad_password in ('too-short', 'x' * 129):
            with self.subTest(password=len(bad_password)):
                status, _, _ = client.post(
                    '/register', {'name': self.unique('pw'), 'password': bad_password})
                self.assertEqual(status, 400)

    # ------------------------------------------------------------------
    # publishing
    # ------------------------------------------------------------------
    def test_create_topic_and_reply(self):
        client, _ = self.make_user('poster')
        location = self.make_topic(client, title='Depot charging in Austin',
                                   category='Cities & regulations',
                                   body='Has anyone seen the permit filings?')
        self.assertTrue(location.startswith('/topic/'))
        topic_id = location.rsplit('/', 1)[1]

        status, _, page = client.get(location)
        self.assertEqual(status, 200)
        self.assertIn('Depot charging in Austin', page)
        self.assertIn('Has anyone seen the permit filings?', page)

        token = client.form_token(location)
        status, _, _ = client.post(f'/reply/{topic_id}',
                                   {'csrf': token, 'body': 'Filed last week, I think.'})
        self.assertEqual(status, 303)
        _, _, page = client.get(location)
        self.assertIn('Filed last week, I think.', page)
        self.assertEqual(self.scalar('SELECT count(*) FROM replies WHERE topic_id=?',
                                     (int(topic_id),)), 1)

    def test_writes_require_a_csrf_token(self):
        client, _ = self.make_user('csrf')
        status, _, _ = client.post('/new', {'csrf': 'forged', 'title': 'x',
                                            'category': 'Technology', 'body': 'y'})
        self.assertEqual(status, 403)
        status, _, _ = client.post('/new', {'title': 'x', 'category': 'Technology',
                                            'body': 'y'})
        self.assertEqual(status, 403)

    def test_writes_require_a_session(self):
        status, headers, _ = self.client().post(
            '/new', {'title': 'x', 'category': 'Technology', 'body': 'y'})
        self.assertEqual(status, 401)

    def test_unknown_category_is_rejected(self):
        client, _ = self.make_user('category')
        token = client.form_token('/new')
        status, _, _ = client.post('/new', {'csrf': token, 'title': 'x',
                                            'category': 'Not A Category', 'body': 'y'})
        self.assertEqual(status, 400)

    def test_post_content_is_html_escaped(self):
        client, _ = self.make_user('escaping')
        payload = '<script>alert(1)</script>'
        self.make_topic(client, title=payload, body=f'{payload} and "quotes"')
        _, _, home = client.get('/')
        self.assertNotIn('<script>alert(1)</script>', home)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', home)

    def test_search_finds_matching_titles(self):
        client, _ = self.make_user('search')
        marker = self.unique('Unobtainium')
        self.make_topic(client, title=f'{marker} cell chemistry')
        _, _, page = client.get(f'/?q={marker}')
        self.assertIn('cell chemistry', page, 'search should return the matching topic')

    # ------------------------------------------------------------------
    # moderation
    # ------------------------------------------------------------------
    def test_moderator_controls_are_hidden_from_regular_members(self):
        client, _ = self.make_user('plain')
        location = self.make_topic(client)
        _, _, page = client.get(location)
        self.assertNotIn('Moderator controls', page)

    def test_regular_member_cannot_lock_or_delete(self):
        author, _ = self.make_user('author')
        location = self.make_topic(author)
        topic_id = location.rsplit('/', 1)[1]

        outsider, _ = self.make_user('outsider')
        token = outsider.form_token(location)
        status, _, _ = outsider.post(f'/lock/{topic_id}', {'csrf': token})
        self.assertEqual(status, 403)
        status, _, _ = outsider.post(f'/delete/{topic_id}',
                                     {'csrf': token, 'confirm': 'yes'})
        self.assertEqual(status, 403)
        self.assertEqual(self.scalar('SELECT count(*) FROM topics WHERE id=?',
                                     (int(topic_id),)), 1)

    def test_moderator_can_lock_and_unlock(self):
        moderator, moderator_name = self.make_user('mod')
        self.promote(moderator_name)
        author, _ = self.make_user('member')
        location = self.make_topic(author)
        topic_id = location.rsplit('/', 1)[1]

        token = moderator.form_token(location)
        _, _, page = moderator.get(location)
        self.assertIn('Moderator controls', page)

        status, _, _ = moderator.post(f'/lock/{topic_id}', {'csrf': token})
        self.assertEqual(status, 303)
        self.assertEqual(self.scalar('SELECT locked FROM topics WHERE id=?',
                                     (int(topic_id),)), 1)

        status, _, page = author.get(location)
        self.assertIn('locked', page)
        self.assertNotIn('Post reply', page)

        # A locked topic refuses replies.
        token = author.form_token(location)
        status, _, _ = author.post(f'/reply/{topic_id}', {'csrf': token, 'body': 'nope'})
        self.assertEqual(status, 403)

        token = moderator.form_token(location)
        status, _, _ = moderator.post(f'/lock/{topic_id}', {'csrf': token})
        self.assertEqual(status, 303)
        self.assertEqual(self.scalar('SELECT locked FROM topics WHERE id=?',
                                     (int(topic_id),)), 0)

    def test_moderator_deletion_removes_replies(self):
        moderator, moderator_name = self.make_user('mod')
        self.promote(moderator_name)
        author, _ = self.make_user('member')
        location = self.make_topic(author)
        topic_id = int(location.rsplit('/', 1)[1])
        token = author.form_token(location)
        author.post(f'/reply/{topic_id}', {'csrf': token, 'body': 'A reply.'})
        self.assertEqual(self.scalar('SELECT count(*) FROM replies WHERE topic_id=?',
                                     (topic_id,)), 1)

        token = moderator.form_token(location)
        status, _, _ = moderator.post(f'/delete/{topic_id}', {'csrf': token})
        self.assertEqual(status, 400, 'deletion must require confirmation')

        token = moderator.form_token(location)
        status, headers, _ = moderator.post(
            f'/delete/{topic_id}', {'csrf': token, 'confirm': 'yes'})
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/')
        self.assertEqual(self.scalar('SELECT count(*) FROM topics WHERE id=?',
                                     (topic_id,)), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM replies WHERE topic_id=?',
                                     (topic_id,)), 0)

    # ------------------------------------------------------------------
    # abuse controls
    # ------------------------------------------------------------------
    def test_repeated_sign_in_attempts_are_rate_limited(self):
        statuses = [self.client().post(
            '/login', {'name': self.unique('flood'), 'password': WRONG_PASSWORD})[0]
            for _ in range(12)]
        self.assertEqual(statuses[:10], [401] * 10)
        self.assertEqual(statuses[10:], [429] * 2)

    def test_rate_limit_tracks_the_forwarded_client_address(self):
        headers = {'X-Forwarded-For': '203.0.113.9, 10.0.0.1'}
        for _ in range(12):
            self.client().post('/login',
                               {'name': 'ghost', 'password': WRONG_PASSWORD},
                               headers=headers)
        same_client = self.client().post(
            '/login', {'name': 'ghost', 'password': WRONG_PASSWORD}, headers=headers)[0]
        self.assertEqual(same_client, 429, 'the same forwarded client must stay limited')

        other_client = self.client().post(
            '/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
            headers={'X-Forwarded-For': '198.51.100.4'})[0]
        self.assertNotEqual(other_client, 429, 'a different client must not be limited')

    def test_rate_limit_uses_cf_connecting_ip_not_the_edge_address(self):
        # The production shape. Cloudflare sets CF-Connecting-IP and appends its
        # own edge address to X-Forwarded-For, so that final entry differs on
        # every single request. Keying on it meant the limiter never fired at
        # all once this was deployed behind Render.
        for edge in range(12):
            self.client().post('/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
                               headers={'CF-Connecting-IP': '203.0.113.50',
                                        'X-Forwarded-For': f'203.0.113.50, 172.71.120.{edge}'})
        status = self.client().post(
            '/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
            headers={'CF-Connecting-IP': '203.0.113.50',
                     'X-Forwarded-For': '203.0.113.50, 172.71.120.250'})[0]
        self.assertEqual(status, 429, 'a stable CF-Connecting-IP must be limited even '
                                      'though the edge entry keeps changing')

    def test_forged_forwarded_for_prefix_cannot_evade_the_limit(self):
        # Any client can prepend entries to X-Forwarded-For. Because Cloudflare
        # overwrites CF-Connecting-IP, the bucket must not move when they do.
        for index in range(12):
            self.client().post('/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
                               headers={'CF-Connecting-IP': '203.0.113.60',
                                        'X-Forwarded-For': f'10.9.9.{index}, 203.0.113.60'})
        status = self.client().post(
            '/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
            headers={'CF-Connecting-IP': '203.0.113.60',
                     'X-Forwarded-For': '10.0.0.1, 203.0.113.60'})[0]
        self.assertEqual(status, 429, 'forging an X-Forwarded-For prefix must not reset the limit')

    def test_rate_limit_falls_back_to_the_entry_before_our_edge(self):
        # With no Cloudflare headers, our own edge appended the final entry, so
        # varying that one must not change the bucket but varying the client must.
        for edge in range(12):
            self.client().post('/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
                               headers={'X-Forwarded-For': f'203.0.113.70, 172.71.120.{edge}'})
        same = self.client().post(
            '/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
            headers={'X-Forwarded-For': '203.0.113.70, 172.71.120.250'})[0]
        self.assertEqual(same, 429)
        other = self.client().post(
            '/login', {'name': 'ghost', 'password': WRONG_PASSWORD},
            headers={'X-Forwarded-For': '203.0.113.71, 172.71.120.250'})[0]
        self.assertNotEqual(other, 429)

    def test_cross_origin_posts_are_refused(self):
        client, _ = self.make_user('origin')
        token = client.form_token('/new')
        status, _, _ = client.post(
            '/new', {'csrf': token, 'title': 'x', 'category': 'Technology', 'body': 'y'},
            headers={'Origin': 'https://evil.example'})
        self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
