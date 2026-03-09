import os, requests, time, json, warnings, sys, re
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
CF_TOKEN = os.getenv("CF_TOKEN")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")

TARGET_URLS = [
    "https://www.consumer.vic.gov.au/latest-news",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=newsalerts",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=mediareleases",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=courtactions",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=enforceableundertakings",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=legislationupdates",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=publicwarnings",
]

MAX_ITEMS = 12

def log(msg): 
    print(f"📝 [LOG] {msg}")
    sys.stdout.flush()

def escape_html(text):
    """Escape HTML special chars for Telegram"""
    if not text:
        return ""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text

def send_telegram(text, reply_id=None):
    log(f"📤 Sending Telegram ({len(text)} chars)...")
    try:
        # ✅ Clean token - remove ALL whitespace
        token = TELEGRAM_TOKEN.replace(" ", "").strip()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        # ✅ Clean chat_id - remove ALL whitespace
        chat_id = CHAT_ID.replace(" ", "").strip()
        
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        if reply_id:
            data["reply_to_message_id"] = reply_id
        
        r = requests.post(url, json=data, timeout=30)
        log(f"📡 Telegram response: {r.status_code} - {r.text[:200]}")
        
        if r.status_code == 200:
            log("✅ Telegram sent successfully")
            return r.json()
        else:
            log(f"❌ Telegram failed: {r.status_code}")
            raise requests.exceptions.HTTPError(f"Telegram {r.status_code}: {r.text[:200]}")
            
    except Exception as e:
        log(f"❌ TELEGRAM FAILED: {type(e).__name__}: {e}")
        raise

def clean_url(href, base):
    if not href:
        return base
    href = href.strip().split()[0]
    if href.startswith(('http://','https://')):
        return href
    if href.startswith('//'):
        return f"https:{href}"
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
                        if len(items) >= MAX_ITEMS:
                            break
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
                            if len(items) >= MAX_ITEMS:
                                break
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    title = link.get_text().strip()
                    href = link.get('href', '')
                    if title and 30 < len(title) < 300 and not any(s in title.lower() for s in ['menu', 'home', 'contact', 'about', 'filter', 'share', 'listen', 'back to', 'page']):
                        full_url = clean_url(href, base) if href else url
                        if full_url.startswith('http') and 'consumer.vic.gov.au' in full_url:
                            items.append(f"[{src}] {title} | {full_url}")
                            if len(items) >= MAX_ITEMS:
                                break
            log(f"✅ HTML {src}: {len(items)} items")
        
        else:
            src = url.split('/')[2].replace('www.','').upper()
            for lk in soup.find_all('a', href=True):
                txt = lk.get_text().strip()
                href = lk['href']
                full = clean_url(href, base)
                if txt and 30 < len(txt) < 300 and full.startswith('http'):
                    if any(s in txt.lower() for s in ['home','contact','about','privacy','menu','skip','page']):
                        continue
                    items.append(f"[{src}] {txt} | {full}")
                    if len(items) >= MAX_ITEMS:
                        break
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
        
        # ✅ SHORTER PROMPT - Less confusing for AI
        prompt = f"""Format these Consumer Affairs VIC news items. LIST ALL ITEMS.

RULES:
1. List EVERY item - do NOT summarize or skip
2. Use <b>bold</b> for headers (NOT **bold**)
3. Each item: • 📋 [SOURCE] Title 🔗 URL
4. Group by: ⚠️ Warnings, 📰 News, ⚖️ Court, 📜 Legislation
5. NO intro text, NO conclusion, NO markdown
6. Max 3500 characters

DATA:
{text[:7000]}

FORMAT:
🛍️ <b>Consumer Affairs VIC News</b>
📅 {time.strftime('%d %b %Y')}

⚠️ <b>Public Warnings</b>
• 📋 [PUBLICWARNINGS] Title 🔗 URL

📰 <b>News & Media</b>
• 📋 [NEWSALERTS] Title 🔗 URL

⚖️ <b>Court & Enforcement</b>
• 📋 [COURTACTIONS] Title 🔗 URL

📜 <b>Legislation</b>
• 📋 [LEGISLATION] Title 🔗 URL"""
        
        log("📡 Posting to Cloudflare AI...")
        r = requests.post(url, headers=headers, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500
        }, timeout=45)
        log(f"✅ AI response: {r.status_code}")
        r.raise_for_status()
        result = r.json()['result']['response'].strip()
        
        if not result or len(result) < 50:
            log("⚠️ AI returned empty/too short response")
            return None
        
        result = result.replace('**', '').replace('`', '').replace('__', '')
        log(f"✅ AI completed ({len(result)} chars)")
        return result
        
    except Exception as e:
        log(f"❌ AI FAILED: {type(e).__name__}: {e}")
        return None

def format_raw_content(all_content):
    """Format raw scraped content without AI (HTML-safe)"""
    header = f"🛍️ Consumer Affairs VIC News\n📅 {time.strftime('%d %b %Y')}\n\n"
    
    sections = {
        "⚠️ <b>Public Warnings</b>": [],
        "📰 <b>News & Media</b>": [],
        "⚖️ <b>Court & Enforcement</b>": [],
        "📜 <b>Legislation</b>": []
    }
    
    for content in all_content:
        for line in content.split('\n'):
            if not line.strip() or line.startswith('❌') or line.startswith('⚠️ No'):
                continue
            
            # Escape HTML special chars
            line = escape_html(line)
            
            # Convert | to 🔗 for raw format
            if ' | ' in line:
                parts = line.split(' | ', 1)
                if len(parts) == 2:
                    line = f"• 📋 {parts[0]} 🔗 {parts[1]}"
            else:
                line = f"• 📋 {line}"
            
            if '[PUBLICWARNINGS]' in line or '[WARNINGS]' in line:
                sections["⚠️ <b>Public Warnings</b>"].append(line)
            elif '[NEWSALERTS]' in line or '[MEDIARELEASES]' in line or '[CONSUMER-VIC]' in line:
                sections["📰 <b>News & Media</b>"].append(line)
            elif '[COURTACTIONS]' in line or '[ENFORCEABLEUNDERTAKINGS]' in line:
                sections["⚖️ <b>Court & Enforcement</b>"].append(line)
            elif '[LEGISLATIONUPDATES]' in line or '[LEGISLATION]' in line:
                sections["📜 <b>Legislation</b>"].append(line)
    
    msg = header
    for section_title, items in sections.items():
        if items:
            msg += f"\n{section_title}\n" + "\n".join(items[:20]) + "\n"
    
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
            if "[" in result and " | " in result:
                working += 1
        
        log(f"📊 COMPLETE: {working}/{len(TARGET_URLS)} sources working")
        content = "\n".join(all_content)
        log(f"📊 Total raw content: {len(content)} chars")
        
        # Try AI first
        summary = call_ai(content)
        
        if not summary:
            log("⚠️ AI failed, using raw formatted content")
            summary = format_raw_content(all_content)
        
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
        token = TELEGRAM_TOKEN.replace(" ", "").strip()
        updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"timeout":1}, timeout=10).json().get("result",[])
        for upd in updates:
            if "message" not in upd:
                continue
            msg = upd["message"]
            if str(msg["chat"]["id"]) != str(CHAT_ID).replace(" ", "").strip():
                continue
            txt = msg.get("text","").strip()
            if not txt.startswith("/") or time.time()-msg.get("date",0)>600:
                continue
            cmd = txt.split()[0].lower()
            if cmd == "/ping":
                return "🏓 Pong"
            elif cmd == "/today":
                send_telegram("🔄 Scanning...", reply_id=msg["message_id"])
                all_content = [scrape_with_links(u) for u in TARGET_URLS]
                summary = call_ai("\n".join(all_content))
                if not summary:
                    summary = format_raw_content(all_content)
                send_telegram(summary)
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
        if check_commands():
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
