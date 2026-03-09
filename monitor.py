import os, requests, time, sys, html
from bs4 import BeautifulSoup

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Removed the main HTML page, kept only the specialized RSS feeds
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
        # Use 'xml' features of lxml (installed via your yml)
        soup = BeautifulSoup(r.content, "xml")
        items = []
        source_label = url.split("RssType=")[-1].upper()

        for entry in soup.find_all('item')[:5]:
            title = html.escape(entry.find('title').text.strip())
            link = entry.find('link').text.strip()
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
        # Format the final report
        header = f"🛍️ <b>Consumer Affairs VIC Update</b>\n📅 {time.strftime('%d %b %Y')}\n\n"
        report = header + "\n\n".join(all_found[:15]) # Limits to top 15 total
        send_telegram(report)
        log("✅ Success: Report sent.")
    else:
        log("🧐 No updates found in any RSS feeds.")

if __name__ == "__main__":
    main()
