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

MAX_ITEMS = 15

def log(msg): 
    print(f"📝 [LOG] {msg}")
    sys.stdout.flush()

def send_telegram(text, reply_id=None):
    log(f"📤 Sending Telegram ({len(text)} chars)...")
    try:
        if len(text) > 4000:
            parts = [text[i:i+3900] for i in range(0, len(text), 3900)]
            for i, part in enumerate(parts):
                if i > 0: time.sleep(1)
                send_single(part, reply_id)
            log(f"✅ Sent {len(parts)} messages")
        else:
            send_single(text, reply_id)
        return True
    except Exception as e:
        log(f"❌ TELEGRAM FAILED: {type(e).__name__}: {e}")
        raise

def send_single(text, reply_id=None):
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
                        items.append(f"[{src}] {txt}{date} | {lnk}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ RSS {src}: {len(items)} items")
        
        elif "consumer.vic.gov.au/latest-news" in url:
            src = "CONSUMER-VIC"
            log(f"📡 Parsing {src} HTML...")
            for article in soup.find_all(['article', 'div'], class_=lambda c: c and any(x in str(c).lower() for x in ['news', 'article', 'item', 'teaser', 'card']) if c else True):
                link = article.find('a', href=True)
                if link:
                    title = link.get_text().strip()
                    href = link.get('href', '')
                    if title and 30 < len(title) < 300 and not any(s in title.lower() for s in ['menu', 'home', 'contact', 'about', 'filter', 'share', 'listen', 'back to']):
                        full_url = clean_url(href, base) if href else url
                        if full_url.startswith('http') and 'consumer.vic.gov.au' in full_url:
                            items.append(f"[{src}] {title} | {full_url}")
                            if len(items) >= MAX_ITEMS: break
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    title = link.get_text().strip()
                    href = link.get('href', '')
                    if title and 30 < len(title) < 300 and not any(s in title.lower() for s in ['menu', 'home', 'contact', 'about', 'filter', 'share', 'listen', 'back to', 'page']):
                        full_url = clean_url(href, base) if href else url
                        if full_url.startswith('http') and 'consumer.vic.gov.au' in full_url:
                            items.append(f"[{src}] {title} | {full_url}")
                            if len(items) >= MAX_ITEMS: break
            log(f"✅ HTML {src}: {len(items)} items")
        
        else:
            src = url.split('/')[2].replace('www.','').upper()
            for lk in soup.find_all('a', href=True):
                txt = lk.get_text().strip()
                href = lk['href']
                full = clean_url(href, base)
                if txt and 30 < len(txt) < 300 and full.startswith('http'):
                    if any(s in txt.lower() for s in ['home','contact','about','privacy','menu','skip','page']): continue
                    items.append(f"[{src}] {txt} | {full}")
                    if len(items) >= MAX_ITEMS: break
            log(f"✅ {src}: {len(items)} items")
        
        result = "\n".join(items[:MAX_ITEMS]) if items else "⚠️ No items"
        log(f"✅ DONE: {url[:50]}... ({len(items)} items)")
        return result
        
    except Exception as e:
        log(f"❌ ERROR {url[:60]}...: {type(e).__name__}: {e}")
        return f"❌ Error: {type(e).__name__}"

def call_ai(text):
    """Format ALL items - NO summarization"""
    log(f"🤖 Calling AI ({len(text)} chars)...")
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
        headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
        
        # ✅ STRICT PROMPT - List EVERY item, NO summarization
        prompt = f"""You are a news formatter. Your job is to format ALL news items provided.

CRITICAL RULES:
1. LIST EVERY SINGLE ITEM - do NOT summarize, condense, or skip any
2. Output MUST be 2000-4000 characters (enough for all 60+ items)
3. Use Telegram HTML: <b>bold</b> NOT **bold** or __bold__
4. Each item keeps its 🔗 link (use 🔗 emoji before URL)
5. Group by source type using these exact headers:
   ⚠️ <b>Public Warnings</b> - for [PUBLICWARNINGS] or [WARNINGS]
   📰 <b>News & Media</b> - for [NEWSALERTS], [MEDIARELEASES], [CONSUMER-VIC]
   ⚖️ <b>Court & Enforcement</b> - for [COURTACTIONS], [ENFORCEABLEUNDERTAKINGS]
   📜 <b>Legislation</b> - for [LEGISLATIONUPDATES] or [LEGISLATION]
6. Format each item as: • 📋 [SOURCE] Title 🔗 URL
7. NO introductory text ("Here is...", "Following is...")
8. NO concluding text ("In summary...", "Next steps...")
9. NO markdown (**, __, ```)
10. Keep titles concise (1 line each)

INPUT DATA (format ALL of this):
{text[:9000]}

OUTPUT FORMAT (EXACTLY):
🛍️ <b>Consumer Affairs VIC News</b>
📅 {time.strftime('%d %b %Y')}

⚠️ <b>Public Warnings</b>
• 📋 [PUBLICWARNINGS] Title 🔗 https://...
• 📋 [CONSUMER-VIC] Title 🔗 https://...

📰 <b>News & Media</b>
• 📋 [NEWSALERTS] Title 🔗 https://...
• 📋 [MEDIARELEASES] Title 🔗 https://...

⚖️ <b>Court & Enforcement</b>
• 📋 [COURTACTIONS] Title 🔗 https://...

📜 <b>Legislation</b>
• 📋 [LEGISLATIONUPDATES] Title 🔗 https://..."""
        
        log("📡 Posting to Cloudflare AI...")
        r = requests.post(url, headers=headers, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000  # ✅ Increased for longer output
        }, timeout=45)
        log(f"✅ AI response: {r.status_code}")
        r.raise_for_status()
        result = r.json()['result']['response'].strip()
        
        # Clean any markdown AI might add
        result = result.replace('**', '').replace('`', '').replace('__', '')
        
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
        
        for i, url in enumerate(TARGET_URLS, 1):
            log(f"📊 [{i}/{len(TARGET_URLS)}] Processing: {url[:50]}...")
            result = scrape_with_links(url)
            all_content.append(result)
            if "📰" in result or "[" in result: working += 1
        
        log(f"📊 COMPLETE: {working}/{len(TARGET_URLS)} sources working")
        content = "\n".join(all_content)
        log(f"📊 Total raw content: {len(content)} chars")
        
        summary = call_ai(content)
        if not summary:
            log("⚠️ AI failed, using raw content")
            summary = f"🛍️ Consumer Affairs VIC News\n📅 {time.strftime('%d %b %Y')}\n\n{content[:3500]}"
        
        log(f"📊 Final message: {len(summary)} chars")
        send_telegram(summary)
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
                content = "\n".join(all_content)
                msg = call_ai(content) or f"🛍️ Consumer Affairs VIC News\n📅 {time.strftime('%d %b')}\n\n{content[:3500]}"
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
