"""
Multi-seed crawler with a continuous freshness loop.

Two usage modes:
  1. Single run:   python crawler.py                 (or --seed / --limit)
  2. Daemon mode:  python crawler.py --daemon        (runs the scheduler forever)

Database lives on the Fly volume at /app/data/search.db and the crawler
UPDATES pages in place on re-crawl rather than duplicating them.
"""
import argparse
import json
import logging
import os
import random
import sqlite3
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from trafilatura import extract

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("crawler")

DB_PATH = os.getenv("DB_PATH", "/app/data/search.db")
SEEDS_FILE = os.getenv("SEEDS_FILE", "/app/seeds.json")
USER_AGENT = os.getenv("CRAWLER_USER_AGENT", "AI-SearchBot/1.0 (+https://example.com/bot)")
HTTP_TIMEOUT = float(os.getenv("CRAWLER_TIMEOUT", "15"))
DEFAULT_INTERVAL = float(os.getenv("CRAWL_INTERVAL_MIN", "30")) * 60
DEFAULT_LIMIT = int(os.getenv("CRAWL_LIMIT", "150"))


def _load_seeds() -> dict:
    cfg = {"seeds": [], "recrawl_minutes": 30, "per_seed_limit": 150}
    if os.path.exists(SEEDS_FILE):
        try:
            with open(SEEDS_FILE) as fh:
                cfg.update(json.load(fh))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read %s: %s", SEEDS_FILE, e)
    if not cfg["seeds"]:
        cfg["seeds"] = ["https://news.ycombinator.com"]
    return cfg


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS pages
        USING fts5(title, content, url UNINDEXED, timestamp UNINDEXED)
        """
    )
    conn.commit()
    return conn


# ---------- politeness / robots ----------
_robots_cache: dict[str, RobotFileParser] = {}


def _allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = _robots_cache.get(robots_url)
    if rp is None:
        rp = RobotFileParser(robots_url)
        try:
            rp.read()
        except Exception:
            rp = None  # no robots → allow
        _robots_cache[robots_url] = rp
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


# ---------- index helpers ----------
def _rowid_for_url(conn: sqlite3.Connection, url: str):
    cur = conn.execute("SELECT rowid FROM pages WHERE url = ?", (url,))
    row = cur.fetchone()
    return row["rowid"] if row else None


def _upsert_page(conn: sqlite3.Connection, title: str, content: str, url: str) -> bool:
    """Insert, or replace existing row so re-crawls refresh instead of duplicate."""
    rowid = _rowid_for_url(conn, url)
    ts = int(time.time())
    if rowid is not None:
        conn.execute(
            "DELETE FROM pages WHERE rowid = ?", (rowid,)
        )
    conn.execute(
        "INSERT INTO pages (title, content, url, timestamp) VALUES (?, ?, ?, ?)",
        (title, content, url, ts),
    )
    return True


def _extract_title(html: str, text: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return " ".join(soup.title.string.split())[:200]
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return "No title"


# ---------- crawler ----------
def crawl_domain(seed_url: str, limit: int) -> int:
    """Crawl one seed hostname up to `limit` newly indexed/refreshed pages."""
    seed_host = urlparse(seed_url).netloc
    conn = init_db()
    to_visit = [seed_url]
    visited = set()
    indexed = 0

    try:
        while to_visit and len(visited) < limit:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            if not _allowed(url):
                logger.info("Blocked by robots.txt: %s", url)
                continue

            logger.info("Crawling: %s", url)
            try:
                resp = requests.get(
                    url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}
                )
                if resp.status_code != 200:
                    continue

                text = extract(
                    resp.text, include_comments=False, include_tables=True, favor_recall=True
                )
                if not text or len(text.strip()) < 100:
                    continue

                title = _extract_title(resp.text, text)
                _upsert_page(conn, title, text.strip(), url)
                conn.commit()
                indexed += 1

                soup = BeautifulSoup(resp.text, "html.parser")
                for link in soup.find_all("a", href=True):
                    full = urljoin(url, link["href"]).split("#")[0]
                    if (
                        urlparse(full).netloc == seed_host
                        and full not in visited
                        and full.startswith(("http://", "https://"))
                    ):
                        to_visit.append(full)

                # be polite: small randomized delay between requests per host
                time.sleep(random.uniform(0.5, 1.5))
            except requests.RequestException as e:
                logger.warning("Request error on %s: %s", url, e)
            except Exception as e:
                logger.warning("Parse error on %s: %s", url, e)
    finally:
        conn.close()

    logger.info("Seed %s done. Visited=%s, Newly indexed/refreshed=%s",
                seed_url, len(visited), indexed)
    return indexed


def refresh_all() -> None:
    cfg = _load_seeds()
    for seed in cfg["seeds"]:
        try:
            crawl_domain(seed, int(cfg.get("per_seed_limit", DEFAULT_LIMIT)))
        except Exception as e:
            logger.exception("Seed %s failed: %s", seed, e)


def run_scheduler(interval_sec: float = DEFAULT_INTERVAL) -> None:
    logger.info("Scheduler starting. Interval=%.0fs", interval_sec)
    while True:
        started = time.time()
        try:
            refresh_all()
        except Exception:
            logger.exception("Scheduler cycle failed")
        elapsed = time.time() - started
        sleep = max(interval_sec - elapsed, 5.0)
        logger.info("Cycle done in %.0fs. Sleeping %.0fs", elapsed, sleep)
        time.sleep(sleep)


# ---------- CLI ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Search Engine crawler")
    parser.add_argument("--daemon", action="store_true",
                        help="Run the refresh scheduler forever")
    parser.add_argument("--seed", type=str, help="Single seed URL to crawl")
    parser.add_argument("--limit", type=int, help="Max pages for a single run")
    args = parser.parse_args()

    if args.daemon:
        run_scheduler()
    elif args.seed:
        crawl_domain(args.seed, args.limit or DEFAULT_LIMIT)
    else:
        refresh_all()
