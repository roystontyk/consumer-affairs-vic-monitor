import os, requests, sys, html
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone # AMENDED

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Melbourne Time Offset (UTC+11)
MELB_TZ = timezone(timedelta(hours=11))

TARGET_URLS = [
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=newsalerts",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=mediareleases",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=courtactions",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=enforceableundertakings",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=legislationupdates",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=publicwarnings",
]

def log(msg): 
    print(f"📝 {msg}", flush=True)

def send_telegram(text):
    log("📤 Sending to Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    r = requests.post(url, json=data, timeout=30)
    if r.status_code != 200:
        log(f"❌ Telegram Error: {r.text}")
    return r.status_code == 200

def scrape_rss(url):
    log(f"🔍 Checking RSS: {url.split('=')[-1]}")
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        # Use 'xml' parser for RSS feeds
        soup = BeautifulSoup(r.content, "xml")
        items = []
        source_label = url.split("RssType=")[-1].upper()

        for entry in soup.find_all('item')[:5]:
            title_node = entry.find('title')
            link_node = entry.find('link')
            if title_node and link_node:
                title = html.escape(title_node.text.strip())
                link = link_node.text.strip()
                items.append(f"• <b>[{source_label}]</b> {title}\n🔗 {link}")
        
        return items
    except Exception as e:
        log(f"⚠️ Failed {url}: {e}")
        return []

def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log("❌ Missing Secrets!")
        return

    all_found = []
    for url in TARGET_URLS:
        all_found.extend(scrape_rss(url))
    
    if all_found:
        # AMENDED: Force Melbourne date
        today_melb = datetime.now(MELB_TZ).strftime('%d %b %Y')
        
        header = f"🛍️ <b>Consumer Affairs VIC Update</b>\n📅 {today_melb}\n\n"
        report = header + "\n\n".join(all_found[:15]) 
        send_telegram(report)
        log("✅ Success: Report sent.")
    else:
        log("🧐 No updates found in any RSS feeds.")

if __name__ == "__main__":
    main()
