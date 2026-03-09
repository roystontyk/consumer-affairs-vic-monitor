import os, requests, time, sys, html
from bs4 import BeautifulSoup

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TARGET_URLS = [
    "https://www.consumer.vic.gov.au/latest-news",
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
    log(f"📤 Sending to Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    r = requests.post(url, json=data, timeout=30)
    if r.status_code != 200:
        log(f"❌ Error: {r.text}")
    return r.status_code == 200

def scrape(url):
    log(f"🔍 Checking: {url}")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=20)
        
        # Determine if RSS or HTML
        is_rss = "RSS.aspx" in url
        soup = BeautifulSoup(r.content, "xml" if is_rss else "html.parser")
        items = []

        if is_rss:
            source = url.split("RssType=")[-1].upper()
            for entry in soup.find_all('item')[:5]: # Get latest 5
                title = html.escape(entry.find('title').text.strip())
                link = entry.find('link').text.strip()
                items.append(f"• <b>[{source}]</b> {title}\n🔗 {link}")
        else:
            # HTML Scraper for latest-news
            for a in soup.find_all('a', href=True):
                title = a.get_text().strip()
                href = a['href']
                if len(title) > 35 and ("/latest-news/" in href or "/news/" in href):
                    full_url = href if href.startswith("http") else f"https://www.consumer.vic.gov.au{href}"
                    items.append(f"• <b>[NEWS]</b> {html.escape(title)}\n🔗 {full_url}")
                    if len(items) >= 5: break
        
        return items
    except Exception as e:
        log(f"⚠️ Failed {url}: {e}")
        return []

def main():
    log("🚀 Script Started")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log("❌ Missing Secrets!")
        return

    all_found = []
    for url in TARGET_URLS:
        results = scrape(url)
        all_found.extend(results)
    
    if all_found:
        # Avoid huge messages: send top 15 total items
        report = f"🛍️ <b>Consumer Affairs VIC Update</b>\n\n" + "\n\n".join(all_found[:15])
        send_telegram(report)
        log("✅ Report sent!")
    else:
        log("🧐 No news found today.")

if __name__ == "__main__":
    main()
