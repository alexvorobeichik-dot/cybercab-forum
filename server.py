import os, sqlite3, secrets, hashlib, hmac, html, json, time, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from http.cookies import SimpleCookie
from pathlib import Path
ROOT=Path(__file__).parent
DB=os.environ.get('FORUM_DB',str(ROOT/'forum.db'))
REGISTRATION_OPEN=os.environ.get('FORUM_REGISTRATION_OPEN','0')=='1'
CATEGORIES=['Cybercab discussion','Ownership & rides','Technology','Cities & regulations','Community']
# The canonical origin for links, canonicals, Open Graph tags and the sitemap.
SITE_URL=os.environ.get('FORUM_SITE_URL','https://teslacybercabforum.com').rstrip('/')
DEFAULT_DESCRIPTION='An independent community for Cybercab discussion, technology, rides and the road ahead.'
class Connection(sqlite3.Connection):
 def __exit__(self, *args):
  try: return super().__exit__(*args)
  finally: self.close()
def connect():
 c=sqlite3.connect(DB,factory=Connection); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init():
 with connect() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,password TEXT NOT NULL,admin INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),csrf TEXT,expires REAL); CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY,title TEXT,body TEXT,category TEXT,user_id INTEGER REFERENCES users(id),created TEXT DEFAULT CURRENT_TIMESTAMP,locked INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS replies(id INTEGER PRIMARY KEY,topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,user_id INTEGER REFERENCES users(id),body TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);''')
def esc(v): return html.escape(str(v),quote=True)
def password(p,salt=None):
 salt=salt or secrets.token_hex(16); return salt+':'+hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
RATE={}
RATE_LOCK=threading.Lock()
RATE_SWEEP=86400
def client_ip(headers,peer):
 # This service runs behind Render, whose ingress is Cloudflare. Cloudflare
 # overwrites CF-Connecting-IP and True-Client-IP with the true client address
 # (and refuses requests that try to supply CF-Connecting-IP themselves), so
 # those are trustworthy. X-Forwarded-For is not: Cloudflare appends its own
 # edge address after the client, so the last entry changes on every request,
 # and any client can prepend forgeable entries to the front.
 for name in ('CF-Connecting-IP','True-Client-IP','X-Real-IP'):
  value=headers.get(name)
  if value and value.strip():return value.strip()
 # Fallback for a plain reverse proxy that only sets X-Forwarded-For. Our own
 # edge appended the final entry, so the client is the one before it. The
 # leading entry is never used: a client can put anything there.
 forwarded=[part.strip() for part in headers.get('X-Forwarded-For','').split(',') if part.strip()]
 if len(forwarded)>=2:return forwarded[-2]
 if forwarded:return forwarded[0]
 return peer
def rate_limited(bucket,key,limit,window):
 now=time.time()
 with RATE_LOCK:
  if len(RATE)>2048:
   for k,(_,start) in list(RATE.items()):
    if now-start>RATE_SWEEP:RATE.pop(k,None)
  count,start=RATE.get((bucket,key),(0,now))
  if now-start>window:count,start=0,now
  count+=1;RATE[(bucket,key)]=(count,start)
  return count>limit
class Handler(BaseHTTPRequestHandler):
 timeout=30
 def send(self,code,body,cookie=None,location=None):
  self.send_response(code); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY'); self.send_header('Referrer-Policy','same-origin'); self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
  if cookie:self.send_header('Set-Cookie',cookie)
  if location:self.send_header('Location',location)
  self.end_headers(); self.wfile.write(body.encode())
 def session(self):
  cookie=SimpleCookie()
  try:cookie.load(self.headers.get('Cookie',''))
  except Exception:return None
  token=cookie['session'].value if 'session' in cookie else ''
  with connect() as c:return c.execute('SELECT users.*,sessions.csrf,sessions.token FROM sessions JOIN users ON users.id=user_id WHERE token=? AND expires>?',(token,time.time())).fetchone()
 def page(self,title,content,user=None,description=None,canonical_path='/',og_type='website'):
  full_title=f'{title} · Cybercab Forum'
  desc=description or DEFAULT_DESCRIPTION
  canonical=SITE_URL+canonical_path
  # Branded share card, generated from the site's own palette and display font.
  # Deliberately not the hero photograph: that one is CC BY-SA and link previews
  # drop the attribution its licence requires.
  image=SITE_URL+'/static/og-card.png'
  nav=f'<a href="/new">Start a discussion</a><span>{esc(user["name"])}</span><form method="post" action="/logout"><input type="hidden" name="csrf" value="{user["csrf"]}"><button class="quiet">Sign out</button></form>' if user else '<a href="/login">Sign in</a><a class="button" href="/register">Join the community</a>'
  return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(full_title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><meta property="og:site_name" content="Cybercab Forum"><meta property="og:type" content="{esc(og_type)}"><meta property="og:title" content="{esc(full_title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:image" content="{esc(image)}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(full_title)}"><meta name="twitter:description" content="{esc(desc)}"><meta name="twitter:image" content="{esc(image)}"><link rel="stylesheet" href="/style.css"></head><body><header><a class="brand" href="/"><img class="brand-mark" src="/static/forum-mark.svg" alt="" width="48" height="48"><b>CYBERCAB <span class="brand-forum">FORUM</span><span class="subtitle">INDEPENDENT COMMUNITY</span></b></a><nav>{nav}</nav></header><main>{content}</main><footer><b>CYBERCAB FORUM</b><p>Independent enthusiast community. Not affiliated with, endorsed by, or sponsored by Tesla, Inc. Tesla and Cybercab are trademarks of their respective owners.</p><a href="/guidelines">Community guidelines & privacy</a></footer></body></html>'''
 def form(self,user,action,fields,label):
  csrf=f'<input type="hidden" name="csrf" value="{user["csrf"]}">' if user else ''
  return f'<form method="post" action="{action}">{csrf}{fields}<button>{label}</button></form>'
 def do_GET(self):
  u=self.session(); path=urlparse(self.path).path; query=parse_qs(urlparse(self.path).query)
  if path=='/healthz':
   with connect() as c:c.execute('SELECT 1').fetchone()
   self.send(200,'ok');return
  if path=='/register' and not REGISTRATION_OPEN:
   self.send(403,self.page('Registration closed','<section class="panel"><h1>Registration is not open yet.</h1><p>The forum is undergoing deployment testing. Please check back later.</p></section>',u));return
  if path=='/static/forum-mark.svg':
   self.send_response(200);self.send_header('Content-Type','image/svg+xml');self.end_headers();self.wfile.write((ROOT/'static'/'forum-mark.svg').read_bytes());return
  if path=='/static/cybercab-web.jpg':
   self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Cache-Control','public, max-age=86400');self.end_headers();self.wfile.write((ROOT/'static'/'cybercab-web.jpg').read_bytes());return
  if path=='/static/og-card.png':
   self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Cache-Control','public, max-age=86400');self.end_headers();self.wfile.write((ROOT/'static'/'og-card.png').read_bytes());return
  if path=='/style.css':
   self.send_response(200);self.send_header('Content-Type','text/css');self.end_headers();self.wfile.write((ROOT/'style.css').read_bytes());return
  if path=='/robots.txt':
   # Note: Render serves its own "disallow all" robots.txt while a free-tier
   # service is spun down. This service is on a paid plan and never spins down,
   # so this handler is always the one that answers.
   body='User-agent: *\nAllow: /\nDisallow: /login\nDisallow: /register\nDisallow: /new\nDisallow: /reply/\nDisallow: /lock/\nDisallow: /delete/\nDisallow: /healthz\n\nSitemap: '+SITE_URL+'/sitemap.xml\n'
   raw=body.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Cache-Control','public, max-age=3600');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
  if path=='/sitemap.xml':
   with connect() as c:
    topics=c.execute('SELECT id,created FROM topics ORDER BY id DESC LIMIT 5000').fetchall()
   entries=['<url><loc>'+esc(SITE_URL+'/')+'</loc></url>','<url><loc>'+esc(SITE_URL+'/guidelines')+'</loc></url>']
   for t in topics:
    lastmod=esc(str(t['created']).replace(' ','T')+'Z') if t['created'] else ''
    entries.append('<url><loc>'+esc(f'{SITE_URL}/topic/{t["id"]}')+'</loc>'+(f'<lastmod>{lastmod}</lastmod>' if lastmod else '')+'</url>')
   body='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(entries)+'</urlset>'
   raw=body.encode('utf-8');self.send_response(200);self.send_header('Content-Type','application/xml; charset=utf-8');self.send_header('Cache-Control','public, max-age=600');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
  content=''; title='Community'; description=None; canonical_path='/'; og_type='website'
  with connect() as c:
   if path=='/':
    q=query.get('q',[''])[0][:100]; cat=query.get('category',[''])[0]
    rows=c.execute('SELECT topics.*,users.name,(SELECT count(*) FROM replies WHERE topic_id=topics.id) replies FROM topics JOIN users ON users.id=topics.user_id WHERE (title LIKE ? OR body LIKE ?) AND (?="" OR category=?) ORDER BY topics.id DESC LIMIT 100',('%'+q+'%','%'+q+'%',cat,cat)).fetchall()
    count=c.execute('SELECT count(*) FROM users').fetchone()[0]; total=c.execute('SELECT count(*) FROM topics').fetchone()[0]
    content=f'''<section class="hero"><div><div class="eyebrow">THE NEXT CHAPTER OF GETTING THERE</div><h1>No steering wheel.<br><em>Plenty to talk about.</em></h1><p>A place to discuss Cybercab, share perspectives, and explore the autonomous road ahead. Built for curious minds. Open to everyone.</p><a class="button" href="{'/new' if u else '/register'}">{'Start a discussion' if u else 'Find your people'} ↗</a></div><figure class="vehicle"><img src="/static/cybercab-web.jpg?v=2" alt="Gold Tesla Cybercab on display at Santana Row" width="11648" height="8736"><figcaption>Photo: <a href="https://commons.wikimedia.org/wiki/File:Tesla_Cybercab_at_Santana_Row_oblique_view_dllu.jpg" target="_blank" rel="noopener">Dllu / Wikimedia Commons</a> · <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a> · cropped to fit</figcaption></figure></section><section class="stats"><span><b>{count}</b> members</span><span><b>{total}</b> discussions</span><span class="live">Independent. Community-driven.</span></section><div class="layout"><aside><h3>Explore the forum</h3><a href="/">All discussions ↗</a>'''
    content+=''.join(f'<a href="/?category={catname.replace("&","%26").replace(" ","%20")}">{esc(catname)}</a>' for catname in CATEGORIES)
    content+='''<div class="note"><div class="eyebrow">A BETTER CONVERSATION</div><p>Be curious. Cite your sources. Disagree respectfully.</p><a href="/guidelines">Read our guidelines →</a></div></aside><section><div class="sectionhead"><h2>Community discussions</h2><a href="/new">+ New topic</a></div><form class="search" method="get"><input name="q" placeholder="Search discussions" aria-label="Search discussions" value="'''+esc(q)+'''"><button>Search</button></form>'''
    for r in rows:
     content+=f'<article class="topic"><span class="tag">{esc(r["category"])}</span><h3><a href="/topic/{r["id"]}">{esc(r["title"])}</a></h3><p>{esc(r["body"][:160])}</p><div class="meta">{esc(r["name"])} · {esc(r["created"])} UTC <span>{r["replies"]} replies {"· Locked" if r["locked"] else ""}</span></div></article>'
    if not rows:content+='<article class="empty"><h3>The conversation starts with you.</h3><p>No discussions here yet. Ask a question or share a thoughtful take.</p><a href="/new">Start the first discussion →</a></article>'
    content+='</section></div>'
   elif path in ['/register','/login']:
    title='Create your account' if path=='/register' else 'Welcome back'
    content=f'<section class="panel"><div class="eyebrow">JOIN THE CONVERSATION</div><h1>{title}</h1><p>Choose a public username. Do not share private information in posts.</p>'+self.form(None,path,'<label>Username<input name="name" minlength="3" maxlength="30" pattern="[A-Za-z0-9_]+" required autocomplete="username"></label><label>Password<input type="password" name="password" minlength="12" maxlength="128" required autocomplete="'+('new-password' if path=='/register' else 'current-password')+'"></label>','Create account' if path=='/register' else 'Sign in')+'<p>Passwords must contain at least 12 characters. By joining you agree to the <a href="/guidelines">guidelines and privacy notice</a>.</p></section>'
   elif path=='/new':
    if not u:self.send(303,'',location='/login');return
    title='Start a discussion'; fields='<label>Title<input name="title" maxlength="160" required></label><label>Category<select name="category">'+''.join(f'<option>{esc(x)}</option>' for x in CATEGORIES)+'</select></label><label>Your post<textarea name="body" rows="8" maxlength="20000" required></textarea></label>'
    content='<section class="panel"><h1>Start a discussion</h1>'+self.form(u,'/new',fields,'Publish discussion')+'</section>'
   elif path.startswith('/topic/'):
    try:tid=int(path.split('/')[-1])
    except ValueError:self.send(404,self.page('Not found','<h1>Topic not found</h1>',u));return
    r=c.execute('SELECT topics.*,users.name FROM topics JOIN users ON users.id=topics.user_id WHERE topics.id=?',(tid,)).fetchone()
    if not r:self.send(404,self.page('Not found','<h1>Topic not found</h1>',u));return
    title=r['title'];description=' '.join(r['body'].split())[:160];canonical_path=f'/topic/{tid}';og_type='article';content=f'<a href="/">← All discussions</a><article class="post"><span class="tag">{esc(r["category"])}</span><h1>{esc(title)}</h1><p class="meta">{esc(r["name"])} · {r["created"]} UTC</p><div class="body">{esc(r["body"])}</div></article><h2>Replies</h2>'
    for reply in c.execute('SELECT replies.*,users.name FROM replies JOIN users ON users.id=replies.user_id WHERE topic_id=? ORDER BY replies.id',(tid,)):
     content+=f'<article class="post"><b>{esc(reply["name"])}</b><small> · {reply["created"]} UTC</small><div class="body">{esc(reply["body"])}</div></article>'
    if u and not r['locked']:content+=self.form(u,f'/reply/{tid}','<label>Your reply<textarea name="body" rows="4" maxlength="20000" required></textarea></label>','Post reply')
    elif not u:content+='<p><a href="/login">Sign in</a> to join the discussion.</p>'
    else:content+='<p>This discussion is locked.</p>'
    if u and u['admin']:content+='<section class="moderation"><h3>Moderator controls</h3>'+self.form(u,f'/lock/{tid}','', 'Unlock topic' if r['locked'] else 'Lock topic')+self.form(u,f'/delete/{tid}','<label><input type="checkbox" name="confirm" value="yes" required> Permanently delete this topic and its replies</label>','Delete topic')+'</section>'
   elif path=='/guidelines':
    title='Guidelines & privacy';canonical_path='/guidelines';description='How the Cybercab Forum is moderated, and what happens to your account, posts and sessions.';content='<section class="panel"><h1>Guidelines & privacy</h1><h2>Keep it constructive</h2><p>No harassment, spam, impersonation, unlawful content, or personal information about others. Distinguish opinions from facts; link to sources for news. Do not post copyrighted material without permission. Moderators may lock or remove topics.</p><h2>Your information</h2><p>This forum stores your public username, a salted password hash, posts, and a seven-day session cookie. Posts and usernames are public. No analytics or advertising trackers are installed. Server access logs may include IP addresses. Do not reuse a sensitive password. Public registration is closed during deployment testing. Administrator access is assigned explicitly by the operator, never automatically to the first registrant.</p><h2>Early community</h2><p>This is an independent enthusiast forum, not a Tesla service. Information here is not financial, legal, or safety advice. For privacy or abuse issues, contact the site administrator by replying to their community welcome topic. The operator must publish a dedicated contact method before public launch.</p></section>'
   else:self.send(404,self.page('Not found','<h1>Page not found</h1>',u));return
  self.send(200,self.page(title,content,u,description=description,canonical_path=canonical_path,og_type=og_type))
 def do_POST(self):
  path=urlparse(self.path).path;u=self.session()
  try:size=int(self.headers.get('Content-Length','0'))
  except ValueError:self.send(400,'Invalid request');return
  if size<0 or size>50000:self.send(413,'Request too large');return
  if path=='/register' and not REGISTRATION_OPEN:
   self.send(403,'Registration is closed during deployment testing.');return
  data=parse_qs(self.rfile.read(size).decode(errors='replace'));get=lambda k:data.get(k,[''])[0].strip()
  def fail(msg,status=400):self.send(status,self.page('Request not completed',f'<section class="panel"><h1>Request not completed</h1><p>{esc(msg)}</p><a href="/">Return to forum</a></section>',u))
  origin=self.headers.get('Origin')
  if origin and urlparse(origin).netloc!=self.headers.get('Host'):fail('Invalid request origin',403);return
  ip=client_ip(self.headers,self.client_address[0])
  if path in ['/register','/login']:
   if rate_limited('auth',ip,10,300):fail('Too many sign-in attempts from this address. Try again in a few minutes.',429);return
  elif rate_limited('write',ip,40,60):fail('Too many requests from this address. Slow down and try again shortly.',429);return
  with connect() as c:
   if path in ['/register','/login']:
    name=get('name');p=get('password')
    if not 3<=len(name)<=30 or not all(x.isascii() and (x.isalnum() or x=='_') for x in name) or not 12<=len(p)<=128:fail('Use a 3–30 character username (letters, numbers, underscores) and a 12–128 character password.');return
    if path=='/register':
     try:
      c.execute('INSERT INTO users(name,password,admin) VALUES(?,?,0)',(name,password(p)))
     except sqlite3.IntegrityError:fail('That username is already registered.');return
    row=c.execute('SELECT * FROM users WHERE name=?',(name,)).fetchone()
    stored=row['password'] if row else '0'*32+':'+'0'*128
    matches=hmac.compare_digest(stored,password(p,stored.split(':')[0]))
    if not row or not matches:fail('Invalid username or password.',401);return
    token=secrets.token_urlsafe(32);c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,row['id'],secrets.token_urlsafe(32),time.time()+604800));c.commit()
    cookie=f'session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'+('; Secure' if os.environ.get('FORUM_SECURE')=='1' else '')
    self.send(303,'',cookie=cookie,location='/');return
   if not u:fail('Please sign in.',401);return
   if not hmac.compare_digest(get('csrf'),u['csrf']):fail('Your form expired. Reload the page and try again.',403);return
   target='/'
   if path=='/logout':
    c.execute('DELETE FROM sessions WHERE token=?',(u['token'],));c.commit();self.send(303,'',cookie='session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/',location='/');return
   elif path=='/new':
    title=get('title');body=get('body');category=get('category')
    if not title or len(title)>160 or not body or len(body)>20000 or category not in CATEGORIES:fail('Check your title, category, and post length.');return
    cur=c.execute('INSERT INTO topics(title,body,category,user_id) VALUES(?,?,?,?)',(title,body,category,u['id']));target=f'/topic/{cur.lastrowid}'
   elif path.startswith(('/reply/','/lock/','/delete/')):
    try:tid=int(path.split('/')[-1])
    except ValueError:fail('Invalid topic');return
    topic=c.execute('SELECT * FROM topics WHERE id=?',(tid,)).fetchone()
    if not topic:fail('Topic not found',404);return
    target=f'/topic/{tid}'
    if path.startswith('/reply/'):
     if topic['locked']:fail('Topic is locked',403);return
     body=get('body')
     if not body or len(body)>20000:fail('Reply must contain 1–20,000 characters.');return
     c.execute('INSERT INTO replies(topic_id,user_id,body) VALUES(?,?,?)',(tid,u['id'],body))
    else:
     if not u['admin']:fail('Moderator access required',403);return
     if path.startswith('/lock/'):c.execute('UPDATE topics SET locked=1-locked WHERE id=?',(tid,))
     else:
      if get('confirm')!='yes':fail('Confirm deletion first');return
      c.execute('DELETE FROM topics WHERE id=?',(tid,));target='/'
   else:fail('Not found',404);return
  self.send(303,'',location=target)
if __name__=='__main__':
 init();port=int(os.environ.get('PORT','8088'));host=os.environ.get('HOST','127.0.0.1');print(f'Cybercab Forum running at http://{host}:{port}',flush=True);http=ThreadingHTTPServer((host,port),Handler);http.socket.settimeout(30);http.serve_forever()
