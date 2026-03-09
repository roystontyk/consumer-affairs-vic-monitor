import os, requests, time, json, warnings, sys, re
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

MAX_ITEMS = 10

def log(msg): 
    print(f"📝 [LOG] {msg}")
    sys.stdout.flush()

def send_telegram(text, reply_id=None):
    log(f"📤 Sending Telegram ({len(text)} chars)...")
    try:
        if len(text) > 4000: 
            text = text[:3950] + "\n\n...(more)"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        if reply_id: data["reply_to_message_id"] = reply_id
        r = requests.post(url, json=data, timeout=30)
        log(f"✅ Telegram: {r.status_code}")
        return r.json()
    except Exception as e:
        log(f"❌ TELEGRAM FAILED: {type(e).__name__}: {e}")
        raise

def clean_url(href, base):
    if not href: return base
    href = href.strip().split()[0]
    if href.startswith(('http://','https://')): return href
    if href.startswith('//'): return f"https:{href}"
    return f"{base}{href}" if href.startswith('/') else f"{base}/{href}"

def remove_duplicates(items):
    """Remove duplicate items based on title similarity"""
    seen = set()
    unique = []
    for item in items:
        title = item.split('🔗')[0].lower().strip()
        title_words = set(title.replace(' - ', ' ').replace(' | ', ' ').split())
        title_key = ' '.join(sorted(title_words))
        if title_key not in seen:
            seen.add(title_key)
            unique.append(item)
    return unique

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
            src = url.split('RssType=')[1] if 'RssType=' in url else url.split('/')[2].upper()
            src = src.replace('.vic.gov.au','').upper()
            for item in soup.find_all('item'):
                t, l = item.find('title'), item.find('link')
                pub = item.find('pubdate')
                if t and l:
                    txt = t.get_text().strip()
                    lnk = l.get_text().strip().split()[0] if l.get_text() else l.get('href', '')
                    lnk = lnk if lnk.startswith('http') else clean_url(lnk, base)
                    date = f" ({pub.get_text().strip()[:16]})" if pub else ""
                    if 20 < len(txt) < 300 and lnk:
                        items.append(f"📰 [{src}] {txt}{date}\n🔗 {lnk}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ RSS {src}: {len(items)} items")
        
        # ✅ HTML NEWS PAGE
        elif "consumer.vic.gov.au/latest-news" in url:
            log("📡 Parsing Consumer Affairs HTML...")
            src = "CONSUMER-VIC"
            articles = soup.find_all('article') or soup.find_all('div', class_=lambda c: c and any(x in str(c).lower() for x in ['news', 'article', 'item', 'teaser']))
            
            for article in articles:
                title_link = article.find('a', href=True)
                if not title_link:
                    title_link = article.find(['h2', 'h3', 'h4'])
                if title_link:
                    title = title_link.get_text().strip()
                    href = title_link.get('href', '') if hasattr(title_link, 'get') else ''
                    full_url = clean_url(href, base) if href else url
                    if title and 20 < len(title) < 300 and full_url.startswith('http'):
                        items.append(f"📰 [{src}] {title}\n🔗 {full_url}")
                        if len(items) >= MAX_ITEMS: break
            
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    title = link.get_text().strip()
                    href = link.get('href', '')
                    if title and 30 < len(title) < 300 and not any(s in title.lower() for s in ['menu', 'home', 'contact', 'about', 'back to', 'filter', 'share']):
                        full_url = clean_url(href, base) if href else url
                        if full_url.startswith('http') and 'consumer.vic.gov.au' in full_url:
                            items.append(f"📰 [{src}] {title}\n🔗 {full_url}")
                            if len(items) >= MAX_ITEMS: break
            log(f"✅ HTML {src}: {len(items)} items")
        
        else:
            src = url.split('/')[2].replace('www.','').upper()
            for art in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower()):
                lk, tt = art.find('a', href=True), art.find(['h2','h3','h4'])
                if lk and tt:
                    txt, href = tt.get_text().strip(), lk['href']
                    full = clean_url(href, base)
                    if 30 < len(txt) < 300:
                        items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ HTML {src}: {len(items)} items")
        
        # ✅ Remove duplicates before returning
        if items:
            items = remove_duplicates(items)
            return f"🌐 {url}\n✅ {len(items)}\n\n" + "\n\n".join(items[:MAX_ITEMS])
        return f"🌐 {url}\n⚠️ None"
        
    except requests.exceptions.Timeout:
        log(f"❌ TIMEOUT: {url[:60]}...")
        return f"🌐 {url}\n⏰ Timeout"
    except Exception as e:
        log(f"❌ ERROR {url[:60]}...: {type(e).__name__}: {e}")
        return f"🌐 {url}\n❌ {type(e).__name__}"

def call_ai(text):
    log(f"🤖 Calling AI ({len(text)} chars)...")
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
        headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
        
        # ✅ STRICT PROMPT - No filler, HTML only, no markdown
        prompt = f"""Consumer Affairs Victoria news. Scams, warnings, court actions, legislation.
RULES:
- Use Telegram HTML: <b>bold</b> NOT **bold**
- Include 🔗 link for EVERY item
- Source labels: [NEWSALERTS],[MEDIARELEASES],[COURTACTIONS],[WARNINGS],[LEGISLATION],[CONSUMER-VIC]
- Group by source type
- Bullet points with emojis
- Max 400 words
- NO introductory text like "Here is..."
- NO markdown formatting (**, `, ```)
- Remove duplicates

News:
{text[:8000]}

FORMAT EXACTLY:
⚠️ <b>Public Warnings</b>
• 📋 [Summary] 🔗 [URL]

📰 <b>News & Media</b>
• 📋 [NEWSALERTS] Summary 🔗 [URL]

⚖️ <b>Court & Enforcement</b>
• 📋 [COURTACTIONS] Summary 🔗 [URL]

📜 <b>Legislation</b>
• 📋 Summary 🔗 [URL]"""
        
        log("📡 Posting to Cloudflare AI...")
        r = requests.post(url, headers=headers, json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}, timeout=30)
        log(f"✅ AI response: {r.status_code}")
        r.raise_for_status()
        result = r.json()['result']['response'].strip()
        
        # ✅ Post-process: Remove any markdown AI might add
        result = result.replace('**', '').replace('`', '').replace('```', '')
        # Remove filler phrases
        for phrase in ['Here is', 'here is', 'Below is', 'Following is', 'I have']:
            if result.startswith(phrase):
                result = result.split('\n\n', 1)[-1] if '\n\n' in result else result
        
        log(f"✅ AI completed ({len(result)} chars)")
        return result
    except Exception as e:
        log(f"❌ AI FAILED: {type(e).__name__}: {e}")
        return None

def run_scheduled():
    log("📰 === RUNNING SCHEDULED DIGEST ===")
    try:
        all_content = []
        working = 0
        total = len(TARGET_URLS)
        
        for i, url in enumerate(TARGET_URLS, 1):
            log(f"📊 [{i}/{total}] Processing: {url[:50]}...")
            result = scrape_with_links(url)
            all_content.append(result)
            if "✅" in result: working += 1
        
        log(f"📊 COMPLETE: {working}/{total} sources working")
        content = "\n\n".join(all_content)
        log(f"📊 Total content: {len(content)} chars")
        
        summary = call_ai(content)
        if not summary:
            log("⚠️ AI failed, using raw content")
            summary = content[:800]
        
        msg = f"🛍️ Consumer Affairs VIC News\n📅 {time.strftime('%d %b %Y')}\n\n{summary}"
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
                content = "\n\n".join([scrape_with_links(u) for u in TARGET_URLS])
                return f"🛍️ Consumer Affairs VIC News\n📅 {time.strftime('%d %b')}\n\n{call_ai(content) or content[:600]}"
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
        if check_commands():
            log("✅ Command handled, exiting")
            return
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
