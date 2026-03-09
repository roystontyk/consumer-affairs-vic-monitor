import os, requests, time, json, warnings, sys, html
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Note: CF tokens are initialized but not currently used in your scraping logic
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
    if not text or "⚠️ No items found" in text:
        log("skipping empty message.")
        return
    
    log(f"📤 Sending Telegram ({len(text)} chars)...")
    try:
        # Telegram limit is 4096. 3900 is a safe buffer.
        if len(text) > 3900:
            parts = [text[i:i+3900] for i in range(0, len(text), 3900)]
            for i, part in enumerate(parts):
                if i > 0: time.sleep(1.5) 
                send_telegram_single(part, reply_id)
        else:
            send_telegram_single(text, reply_id)
        return True
    except Exception as e:
        log(f"❌ TELEGRAM FAILED: {e}")
        raise

def send_telegram_single(text, reply_id=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Ensure all HTML tags are closed or text is escaped to prevent 400 errors
    data = {
        "chat_id": CHAT_ID, 
        "text": text, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": False
    }
    if reply_id: data["reply_to_message_id"] = reply_id
    r = requests.post(url, json=data, timeout=30)
    if r.status_code != 200:
        log(f"❌ Telegram Error Details: {r.text}")
    r.raise_for_status()
    return r.json()

def clean_url(href, base):
    if not href: return base
    href = href.strip().split()[0]
    if href.startswith(('http://','https://')): return href
    if href.startswith('//'): return f"https:{href}"
    return f"{base}{href}" if href.startswith('/') else f"{base}/{href}"
