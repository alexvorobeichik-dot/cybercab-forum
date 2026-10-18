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

    def request(self, method, path, data=None, headers=None):
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
            payload = response.read().decode('utf-8', 'replace')
            self._remember(response.headers)
            return response.status, response.headers, payload
        finally:
            connection.close()

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
        status, headers, body = self.client().get('/static/og-card.png')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertTrue(body.startswith('\x89PNG\r\n'))

    def test_topic_pages_use_article_metadata(self):
        client, _ = self.make_user('article')
        location = self.make_topic(
            client, title='Metadata topic',
            body='The quick brown fox jumps over the lazy dog.')
        _, _, body = self.client().get(location)
        self.assertIn(f'<link rel="canonical" href="{server.SITE_URL}{location}">', body)
        self.assertIn('<meta property="og:type" content="article">', body)
        self.assertIn('The quick brown fox jumps over the lazy dog.', body)

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
