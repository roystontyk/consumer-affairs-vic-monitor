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
                        if full_url.startswith('http') and 'consumer.vic.gov.au' in full_url:
                            items.append(f"• 📰 [{src}] {title}\n🔗 {full_url}")
                            if len(items) >= MAX_ITEMS: break
            
            # Fallback: grab all meaningful links
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    title = link.get_text().strip()
                    href = link.get('href', '')
                    if title and 30 < len(title) < 300 and not any(s in title.lower() for s in ['menu', 'home', 'contact', 'about', 'filter', 'share', 'listen', 'back to', 'page']):
                        full_url = clean_url(href, base) if href else url
                        if full_url.startswith('http') and 'consumer.vic.gov.au' in full_url:
                            items.append(f"• 📰 [{src}] {title}\n🔗 {full_url}")
                            if len(items) >= MAX_ITEMS: break
            
            log(f"✅ HTML {src}: {len(items)} items")
        
        else:
            src = url.split('/')[2].replace('www.','').upper()
            log(f"📡 Parsing {src}...")
            for lk in soup.find_all('a', href=True):
                txt = lk.get_text().strip()
                href = lk['href']
                full = clean_url(href, base)
                if txt and 30 < len(txt) < 300 and full.startswith('http'):
                    if any(s in txt.lower() for s in ['home','contact','about','privacy','menu','skip','page']): continue
                    items.append(f"• 📰 [{src}] {txt}\n🔗 {full}")
                    if len(items) >= MAX_ITEMS: break
            log(f"✅ {src}: {len(items)} items")
        
        result = "\n\n".join(items[:MAX_ITEMS]) if items else "⚠️ No items found"
        log(f"✅ DONE: {url[:50]}... ({len(items)} items)")
        return result
        
    except Exception as e:
        log(f"❌ ERROR {url[:60]}...: {type(e).__name__}: {e}")
        return f"❌ Error: {type(e).__name__}"

def format_digest(all_content):
    """Format scraped content WITHOUT AI summarization"""
    header = f"🛍️ Consumer Affairs VIC News\n📅 {time.strftime('%d %b %Y')}\n\n"
    
    # Group by source type
    sections = {
        "⚠️ Public Warnings": [],
        "📰 News & Media": [],
        "⚖️ Court & Enforcement": [],
        "📜 Legislation": []
    }
    
    for content in all_content:
        for line in content.split('\n\n'):
            if not line.strip(): continue
            if '[PUBLICWARNINGS]' in line or '[WARNINGS]' in line:
                sections["⚠️ Public Warnings"].append(line)
            elif '[NEWSALERTS]' in line or '[MEDIARELEASES]' in line or '[CONSUMER-VIC]' in line:
                sections["📰 News & Media"].append(line)
            elif '[COURTACTIONS]' in line or '[ENFORCEABLEUNDERTAKINGS]' in line:
                sections["⚖️ Court & Enforcement"].append(line)
            elif '[LEGISLATIONUPDATES]' in line or '[LEGISLATION]' in line:
                sections["📜 Legislation"].append(line)
    
    # Build message
    msg = header
    for section_title, items in sections.items():
        if items:
            msg += f"\n{section_title}\n" + "\n".join(items[:15]) + "\n"
    
    return msg

def run_scheduled():
    log("📰 === RUNNING SCHEDULED DIGEST ===")
    try:
        all_content = []
        working = 0
        
        for i, url in enumerate(TARGET_URLS, 1):
            log(f"📊 [{i}/{len(TARGET_URLS)}] Processing: {url[:50]}...")
            result = scrape_with_links(url)
            all_content.append(result)
            if "📰" in result or "•" in result: working += 1
        
        log(f"📊 COMPLETE: {working}/{len(TARGET_URLS)} sources working")
        
        # ✅ FORMAT WITHOUT AI (shows ALL items)
        msg = format_digest(all_content)
        log(f"📊 Final message: {len(msg)} chars")
        
        send_telegram(msg)
        log("✅ === DIGEST SENT SUCCESSFULLY ===")
        
    except Exception as e:
        log(f"❌ === RUN_SCHEDULED FAILED: {type(e).__name__}: {e} ===")
        import traceback
        log(traceback.format_exc())
        raise

def check_commands():
    try:
        log("🔍 Checking Telegram commands...")
        updates = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", params={"timeout":1}, timeout=10).json().get("result",[])
        for upd in updates:
            if "message" not in upd: continue
            msg = upd["message"]
            if str(msg["chat"]["id"]) != str(CHAT_ID): continue
            txt = msg.get("text","").strip()
            if not txt.startswith("/") or time.time()-msg.get("date",0)>600: continue
            cmd = txt.split()[0].lower()
            if cmd == "/ping": return "🏓 Pong"
            elif cmd == "/today":
                send_telegram("🔄", reply_id=msg["message_id"])
                all_content = [scrape_with_links(u) for u in TARGET_URLS]
                msg = f"🛍️ Consumer Affairs VIC News\n📅 {time.strftime('%d %b')}\n\n" + format_digest(all_content)
                send_telegram(msg)
                return None
        return None
    except Exception as e:
        log(f"❌ Command check failed: {e}")
        return None

def main():
    log("🔍 === SCRIPT STARTING ===")
    log(f"🔑 TELEGRAM_TOKEN: {'✅ Set' if TELEGRAM_TOKEN else '❌ MISSING'}")
    log(f"🔑 CHAT_ID: {'✅ Set' if CHAT_ID else '❌ MISSING'}")
    log(f"🔑 CF_TOKEN: {'✅ Set' if CF_TOKEN else '❌ MISSING'}")
    log(f"🔑 CF_ACCOUNT_ID: {'✅ Set' if CF_ACCOUNT_ID else '❌ MISSING'}")
    
    try:
        if check_commands(): return
        log("📰 No commands, running scheduled digest...")
        run_scheduled()
        log("✅ === SCRIPT COMPLETED SUCCESSFULLY ===")
    except Exception as e:
        log(f"❌ === MAIN FAILED: {type(e).__name__}: {e} ===")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
