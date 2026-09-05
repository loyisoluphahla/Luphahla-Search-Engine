import sqlite3
import requests
from trafilatura import extract
from urllib.parse import urljoin, urlparse
import time
from bs4 import BeautifulSoup

DB_PATH = "/app/search.db"  # This matches the Fly volume mount

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(title, content, url, timestamp)")
    conn.commit()
    return conn

def crawl_seed(seed_url="https://news.ycombinator.com", limit=50):
    conn = init_db()
    to_visit = [seed_url]
    visited = set()
    
    while to_visit and len(visited) < limit:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        print(f"Crawling: {url}")
        
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "MyBot/1.0"})
            if resp.status_code != 200:
                continue
            
            text = extract(resp.text, include_comments=False, include_tables=True)
            if not text or len(text) < 100:
                continue
            
            title = text.split('\n')[0][:100] if text else "No title"
            
            conn.execute("INSERT INTO pages (title, content, url, timestamp) VALUES (?, ?, ?, ?)",
                         (title, text, url, int(time.time())))
            conn.commit()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            for link in soup.find_all('a', href=True):
                full_url = urljoin(url, link['href'])
                if urlparse(full_url).netloc == urlparse(seed_url).netloc:
                    if full_url not in visited:
                        to_visit.append(full_url)
        except Exception as e:
            print(f"Error on {url}: {e}")
    conn.close()
    print(f"✅ Indexed {len(visited)} pages.")

if __name__ == "__main__":
    crawl_seed()
