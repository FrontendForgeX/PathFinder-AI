"""PathFinder research service.

Search discovery uses SerpApi. Matching, date detection, and page research
are intentionally rule-based; any unconfirmed detail is marked as such.
"""

import os, re, json, time, hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests, serpapi
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
ROOT = Path(__file__).parent
load_dotenv(ROOT / '.env')
app = Flask(__name__)
CACHE = ROOT / 'cache'
CACHE.mkdir(exist_ok=True)
SAVED = ROOT / 'saved.json'
MONTH = '(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
DATE_PATTERNS = [re.compile(f'\\b{MONTH}\\s+\\d{{1,2}}\\s*[-–]\\s*{MONTH}\\s+\\d{{1,2}},?\\s+\\d{{2,4}}\\b', re.I), re.compile(f'\\b{MONTH}\\s+\\d{{1,2}}\\s*[-–]\\s*\\d{{1,2}},?\\s+\\d{{4}}\\b', re.I), re.compile(f'\\b{MONTH}\\s+\\d{{1,2}},?\\s+\\d{{4}}\\b', re.I)]
MONTHS = {m.lower(): i for i, m in enumerate(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'], 1)}

def month_number(word):
    return next((n for m, n in MONTHS.items() if m.startswith(word.lower()[:3])), None)

def date_bounds(raw):
    if not raw:
        return (None, None)
    s = raw.replace('–', '-').replace(',', '').strip()
    try:
        a = re.fullmatch('([A-Za-z]+)\\s+(\\d{1,2})\\s*-\\s*([A-Za-z]+)\\s+(\\d{1,2})\\s+(\\d{2,4})', s)
        if a:
            m1, d1, m2, d2, y = a.groups()
            y = int(y)
            y = y + 2000 if y < 100 else y
            start = date(y, month_number(m1), int(d1))
            end = date(y, month_number(m2), int(d2))
            if end < start:
                start = date(y - 1, month_number(m1), int(d1))
            return (start, end)
        a = re.fullmatch('([A-Za-z]+)\\s+(\\d{1,2})\\s*-\\s*(\\d{1,2})\\s+(\\d{4})', s)
        if a:
            m, d1, d2, y = a.groups()
            return (date(int(y), month_number(m), int(d1)), date(int(y), month_number(m), int(d2)))
        a = re.fullmatch('([A-Za-z]+)\\s+(\\d{1,2})\\s+(\\d{4})', s)
        if a:
            m, d, y = a.groups()
            d = date(int(y), month_number(m), int(d))
            return (d, d)
    except (ValueError, TypeError):
        pass
    return (None, None)

def find_dates(text):
    matches = []
    used = set()
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text or ''):
            if any((m.start() >= a and m.end() <= b for a, b in used)):
                continue
            used.add((m.start(), m.end()))
            nearby = text[max(0, m.start() - 85):min(len(text), m.end() + 85)].lower()
            if re.search('editorial|published|last updated|publication|posted on', nearby):
                kind = 'ARTICLE_DATE'
            elif re.search('registration deadline|registration closes|apply by|register by|submission deadline|last date|deadline', nearby):
                kind = 'DEADLINE'
            elif re.search('hackathon|event|takes place|held on|scheduled for|begins on|starts on|finale', nearby):
                kind = 'EVENT_DATE'
            else:
                kind = 'UNKNOWN'
            matches.append({'text': m.group(), 'kind': kind, 'position': m.start()})
    return sorted(matches, key=lambda x: x['position'])

def extract_dates(text):
    dates = find_dates(text)
    event = next((d['text'] for d in dates if d['kind'] == 'EVENT_DATE'), None)
    deadline = next((d['text'] for d in dates if d['kind'] == 'DEADLINE'), None)
    return (event, deadline)

def event_status(raw):
    start, end = date_bounds(raw)
    if not start or not end:
        return 'UNKNOWN'
    today = date.today()
    return 'UPCOMING' if today < start else 'ONGOING' if today <= end else 'ENDED'

def domain(url):
    return urlparse(url).netloc.lower().removeprefix('www.')

def page_kind(url, title):
    host = domain(url)
    t = title.lower()
    if any((x in host for x in ('linkedin.com', 'instagram.com', 'facebook.com', 'x.com'))):
        return 'SOCIAL'
    if any((x in t for x in ('complete list', 'top hackathons', 'best hackathons', 'upcoming hackathons', 'hackathons in india 2026 / 2027', 'leading hackathons'))):
        return 'DIRECTORY_OR_ARTICLE'
    if any((x in host for x in ('thehindu.com', 'timesofindia.indiatimes.com', 'reskilll.com'))):
        return 'ARTICLE'
    if any((x in host for x in ('unstop.com', 'devpost.com', 'hack2skill.com'))):
        return 'EVENT_PAGE'
    return 'UNVERIFIED'

def fetch_page(url):
    host = domain(url)
    if not url.startswith(('https://', 'http://')) or host in ('localhost', '127.0.0.1') or (not host):
        return ''
    import ipaddress, socket
    try:
        addresses = socket.getaddrinfo(host, None)
        if any((not ipaddress.ip_address(info[4][0]).is_global for info in addresses)):
            return ''
    except (OSError, ValueError):
        return ''
    try:
        r = requests.get(url, timeout=7, allow_redirects=False, headers={'User-Agent': 'Mozilla/5.0 PathFinderAI/1.0'})
        if r.status_code != 200 or 'text/html' not in r.headers.get('content-type', ''):
            return ''
        soup = BeautifulSoup(r.text[:500000], 'html.parser')
        for tag in soup(['script', 'style', 'svg', 'noscript', 'header', 'footer', 'nav']):
            tag.decompose()
        return re.sub('\\s+', ' ', soup.get_text(' ', strip=True))[:30000]
    except requests.RequestException:
        return ''

def key_for(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()[:16]

def queries_for(p):
    year = date.today().year
    interest = p['interests'].replace(',', ' ')
    return [f'{interest} student hackathon India {year} registration', f"{p['branch']} engineering hackathon {year} India apply", f"hackathon {p['location']} {year} registration", f'student hackathon {year} online free registration India', f'{interest} student innovation competition {year} India']

def get_results(p, refresh=False):
    file = CACHE / (key_for(p) + '.json')
    if file.exists() and (not refresh):
        try:
            return (json.loads(file.read_text(encoding='utf-8')), 'cached', [])
        except (OSError, ValueError):
            pass
    api = os.getenv('SERPAPI_KEY', '').strip()
    if not api:
        return ([], 'missing_key', ['Add SERPAPI_KEY to .env to run live searches.'])
    client = serpapi.Client(api_key=api, timeout=18)
    raw = []
    errors = []
    for q in queries_for(p):
        try:
            result = client.search({'engine': 'google', 'q': q, 'num': 10, 'gl': 'in', 'hl': 'en'})
            raw.extend(result.get('organic_results', []))
        except Exception as exc:
            errors.append(f'Search failed for {q}: {str(exc)[:100]}')
    if raw:
        file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
    return (raw, 'live' if raw else 'failed', errors)

def matches(word, text):
    return bool(word.strip() and re.search('(?<!\\w)' + re.escape(word.strip()) + '(?!\\w)', text, re.I))

def make_opportunities(raw, p, research=True):
    seen = set()
    items = []
    skills = [x.strip() for x in p['skills'].split(',') if x.strip()]
    interests = [x.strip() for x in p['interests'].split(',') if x.strip()]
    for r in raw:
        url = r.get('link', '')
        title = r.get('title', '')
        snippet = r.get('snippet', '')
        if not url.startswith('https://') or url in seen:
            continue
        seen.add(url)
        text = title + ' ' + snippet
        host = domain(url)
        if any((x in host for x in ('youtube.com', 'pinterest.com', 'scribd.com', 'instagram.com'))):
            continue
        if not re.search('hackathon|competition|challenge|innovation|coding contest', text, re.I):
            continue
        kind = page_kind(url, title)
        score = 30 if matches('hackathon', text) else 15
        reasons = []
        for interest in interests:
            if matches(interest, text):
                score += 15
                reasons.append('Interest: ' + interest)
        for skill in skills:
            if matches(skill, text):
                score += 8
                reasons.append('Skill: ' + skill)
        if matches(p['location'], text):
            score += 15
            reasons.append('Preferred location')
        if re.search('\\bstudents?\\b', text, re.I):
            score += 10
            reasons.append('Student-friendly description')
        if re.search('register|apply now|registration', text, re.I):
            score += 12
        if kind == 'EVENT_PAGE':
            score += 30
        elif kind == 'DIRECTORY_OR_ARTICLE':
            score -= 35
        elif kind == 'ARTICLE':
            score -= 20
        elif kind == 'SOCIAL':
            score -= 40
        if re.search('participated|was held|successfully completed|results announced', text, re.I):
            score -= 35
        event, deadline = extract_dates(text)
        items.append({'id': hashlib.sha256(url.encode()).hexdigest()[:16], 'name': title, 'description': snippet, 'url': url, 'source': host, 'kind': kind, 'score': max(0, score), 'reasons': reasons[:3], 'event_date': event, 'deadline': deadline, 'status': event_status(event), 'registration': 'UNVERIFIED', 'mode': 'UNKNOWN', 'research_source': 'SNIPPET'})
    items.sort(key=lambda x: x['score'], reverse=True)
    if research:
        for item in items[:5]:
            if item['kind'] in ('ARTICLE', 'DIRECTORY_OR_ARTICLE', 'SOCIAL'):
                continue
            text = fetch_page(item['url'])
            if len(text) < 200:
                continue
            item['research_source'] = 'WEBPAGE'
            event, deadline = extract_dates(text)
            if event:
                item['event_date'] = event
            if deadline:
                item['deadline'] = deadline
            item['status'] = event_status(item['event_date'])
            if re.search('registration closed|registrations closed|applications closed', text, re.I):
                item['registration'] = 'CLOSED SIGNAL'
            elif re.search('registration open|registrations open|register now|apply now', text, re.I):
                item['registration'] = 'OPEN SIGNAL (VERIFY)'
            online = bool(re.search('\\bonline\\b|\\bvirtual\\b|\\bremote\\b', text, re.I))
            offline = bool(re.search('\\boffline\\b|in.person|on.campus|\\bvenue\\b', text, re.I))
            item['mode'] = 'HYBRID (UNVERIFIED)' if online and offline else 'ONLINE SIGNAL' if online else 'OFFLINE SIGNAL' if offline else 'UNKNOWN'
    return items

def read_saved():
    try:
        return json.loads(SAVED.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []

@app.get('/')
def home():
    return render_template('index.html')

@app.post('/api/search')
def search():
    p = {k: str(request.get_json(silent=True).get(k, '')).strip()[:150] for k in ('branch', 'year', 'skills', 'interests', 'location')} if isinstance(request.get_json(silent=True), dict) else {}
    if not p or not all(p.values()):
        return (jsonify({'error': 'Complete all profile fields.'}), 400)
    refresh = bool(request.get_json().get('refresh', False))
    raw, source, errors = get_results(p, refresh)
    items = make_opportunities(raw, p)
    return jsonify({'items': items, 'source': source, 'errors': errors, 'queries': queries_for(p), 'total': len(items)})

@app.route('/api/saved', methods=['GET', 'POST'])
def saved():
    if request.method == 'GET':
        return jsonify(read_saved())
    data = request.get_json(silent=True) or {}
    item = data.get('item', {})
    if not isinstance(item, dict) or not str(item.get('url', '')).startswith('https://'):
        return (jsonify({'error': 'Invalid opportunity'}), 400)
    current = read_saved()
    current = [x for x in current if x.get('url') != item['url']]
    if data.get('remove') is not True:
        current.append({k: item.get(k) for k in ('id', 'name', 'url', 'source', 'score', 'status', 'deadline', 'event_date', 'description')})
    SAVED.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    return jsonify({'saved': len(current)})
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
