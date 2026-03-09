import os, requests, time, json, warnings, sys
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

TARGET_URLS = [
    "https://www.consumer.vic.gov.au/latest-news",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=newsalerts",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=mediareleases",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=courtactions",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=enforceableundertakings",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=legislationupdates",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=publicwarnings",
]

MAX_ITEMS = 15  # Per source

def log(msg): 
    print(f"📝 [LOG] {msg}")
    sys.stdout.flush()

def send_telegram(text, reply_id=None):
    log(f"📤 Sending Telegram ({len(text)} chars)...")
    try:
        # Split into multiple messages if too long
        if len(text) > 4000:
            parts = [text[i:i+3900] for i in range(0, len(text), 3900)]
            for i, part in enumerate(parts):
                if i > 0: time.sleep(1)  # Avoid rate limiting
                send_telegram_single(part, reply_id)
            log(f"✅ Sent {len(parts)} messages")
        else:
            send_telegram_single(text, reply_id)
        return True
    except Exception as e:
        log(f"❌ TELEGRAM FAILED: {type(e).__name__}: {e}")
        raise

def send_telegram_single(text, reply_id=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    if reply_id: data["reply_to_message_id"] = reply_id
    r = requests.post(url, json=data, timeout=30)
    log(f"✅ Telegram: {r.status_code}")
    r.raise_for_status()
    return r.json()

def clean_url(href, base):
    if not href: return base
    href = href.strip().split()[0]
    if href.startswith(('http://','https://')): return href
    if href.startswith('//'): return f"https:{href}"
    return f"{base}{href}" if href.startswith('/') else f"{base}/{href}"

def scrape_with_links(url):
    start = time.time()
    try:
        log(f"🔍 Scraping: {url[:60]}...")
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        log(f"✅ HTTP OK ({r.status_code}) in {time.time()-start:.1f}s")
        
        soup = BeautifulSoup(r.content, "html.parser")
        items, base = [], "/".join(url.split("/")[:3])
        is_rss = "rss.aspx" in url.lower() or ".rss" in url.lower()
        
        # ✅ RSS FEEDS
        if is_rss:
            src = url.split('RssType=')[1] if 'RssType=' in url else 'RSS'
            src = src.replace('.vic.gov.au','').replace('aspx','').upper().strip()
            for item in soup.find_all('item'):
                t, l = item.find('title'), item.find('link')
                pub = item.find('pubdate')
                if t and l:
                    txt = t.get_text().strip()
                    lnk = l.get_text().strip().split()[0] if l.get_text() else l.get('href', '')
                    lnk = lnk if lnk.startswith('http') else clean_url(lnk, base)
                    date = f" ({pub.get_text().strip()[:16]})" if pub else ""
                    if 20 < len(txt) < 300 and lnk:
                        items.append(f"• 📰 [{src}] {txt}{date}\n🔗 {lnk}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ RSS {src}: {len(items)} items")
        
        # ✅ HTML NEWS PAGE
        elif "consumer.vic.gov.au/latest-news" in url:
            src = "CONSUMER-VIC"
            log(f"📡 Parsing {src} HTML...")
            
            # Look for article elements or news links
            for article in soup.find_all(['article', 'div'], class_=lambda c: c and any(x in str(c).lower() for x in ['news', 'article', 'item', 'teaser', 'card']) if c else True):
                link = article.find('a', href=True)
                if link:
                    title = link.get_text().strip()
                    href = link.get('href', '')
                    if title and 30 < len(title) < 300 and not any(s in title.lower() for s in ['menu', 'home', 'contact', 'about', 'filter', 'share', 'listen', 'back to']):
                        full_url = clean_url(href, base) if href else url
                        if full_url
