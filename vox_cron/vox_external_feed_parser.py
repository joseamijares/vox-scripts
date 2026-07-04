#!/usr/bin/env python3
"""
VOX External Feed Parser v0.2
Scrapes Fiscal.ai blog (manual fallback) and Grit Alpha sitemap (automated) for stock ideas.
Extracts tickers, adds them to discovery_queue, and writes an Obsidian note.
"""
import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime, date
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": 35577,
    "user": "postgres",
    "password": os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD"),
    "dbname": "railway",
}

OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian" / "VOX" / "ExternalFeeds"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")


def fetch(url, timeout=20):
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Fetch error {url}: {e}")
        return ""


class GritArchiveParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.posts = []
        self._href = None
        self._title = None
        self._capture = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if tag == "a" and href and href.startswith("https://grit-alpha.beehiiv.com/p/"):
            self._href = href
            self._title = None
            self._capture = True

    def handle_data(self, data):
        if self._capture and self._href is not None:
            self._title = (self._title or "") + data

    def handle_endtag(self, tag):
        if tag == "a" and self._capture:
            title = (self._title or "").strip()
            if title and self._href:
                self.posts.append({"title": title, "url": self._href, "source": "grit"})
            self._href = None
            self._title = None
            self._capture = False


def parse_grit_sitemap():
    """Fetch Grit Alpha sitemap and return recent post URLs."""
    xml = fetch("https://grit-alpha.beehiiv.com/sitemap.xml")
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    posts = []
    for u in root.findall("ns:url", ns):
        loc = u.find("ns:loc", ns)
        lastmod = u.find("ns:lastmod", ns)
        if loc is None or loc.text is None:
            continue
        if "/p/" not in loc.text:
            continue
        try:
            if lastmod is not None and lastmod.text:
                post_date = date.fromisoformat(lastmod.text[:10])
            else:
                post_date = None
        except ValueError:
            post_date = None
        posts.append({"title": "", "url": loc.text, "source": "grit", "post_date": post_date})
    return posts


def parse_grit_archive():
    """Fallback: parse the public archive page."""
    html = fetch("https://grit-alpha.beehiiv.com/")
    if not html:
        return []
    parser = GritArchiveParser()
    parser.feed(html)
    return parser.posts


def extract_tickers(text):
    if not text:
        return []
    return list(set(TICKER_RE.findall(text)))


def fetch_post_title(url):
    """Fetch the real <title> tag from a post page; fall back to URL slug."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if m:
                title = re.sub(r"\s+", " ", m.group(1).strip())
                if title and title not in ("GritALPHA", ""):
                    return title
    except Exception:
        pass
    slug = url.split("/p/")[-1].replace("-", " ").title()
    for suffix in [" Stock", " Analysis", " Deep Dive"]:
        if slug.endswith(suffix):
            slug = slug[:-len(suffix)]
    return slug


def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS external_feed_ideas (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            feed_source TEXT NOT NULL,
            post_title TEXT,
            post_url TEXT,
            post_date DATE,
            discovered_at DATE DEFAULT CURRENT_DATE,
            added_to_discovery BOOLEAN DEFAULT FALSE,
            UNIQUE(ticker, feed_source, post_url, discovered_at)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_external_feed_ideas_discovered
        ON external_feed_ideas(discovered_at, feed_source);
    """)


def add_to_discovery(cur, ticker, source, title, url):
    try:
        source_text = f"{source}: {title or url or ''}"[:45]
        cur.execute("""
            INSERT INTO discovery_queue (ticker, vox_grade, discovery_source, status, created_at)
            VALUES (%s, NULL, %s, 'pending', NOW())
            ON CONFLICT (ticker, status) DO NOTHING
        """, (ticker, source_text))
        return True
    except Exception as e:
        print(f"Error adding {ticker} to discovery: {e}")
        return False


def persist_ideas(cur, ideas):
    for idea in ideas:
        cur.execute("""
            INSERT INTO external_feed_ideas (ticker, feed_source, post_title, post_url, post_date, discovered_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT (ticker, feed_source, post_url, discovered_at) DO NOTHING
        """, (idea["ticker"], idea["source"], idea.get("title"), idea["url"], idea.get("post_date")))


def write_obsidian(ideas):
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = OBSIDIAN_DIR / f"ExternalFeeds-{date_str}.md"

    by_source = {}
    for idea in ideas:
        by_source.setdefault(idea["source"], []).append(idea)

    lines = [f"# VOX External Feed Ideas — {date_str}", ""]
    for source, items in by_source.items():
        lines.append(f"## {source.title()} Feed")
        lines.append("| Ticker | Post | Source URL |")
        lines.append("|--------|------|------------|")
        for item in items:
            title = item.get("title") or fetch_post_title(item["url"])
            lines.append(f"| {item['ticker']} | {title} | {item['url']} |")
        lines.append("")

    path.write_text("\n".join(lines))
    return path


def parse_fiscal_manual():
    """
    Fiscal.ai is behind Vercel Security Checkpoint for headless requests.
    This function returns an empty list; use the browser-assisted helper or
    populate the table manually from a browser snapshot.
    """
    return []


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        ensure_tables(cur)

        # Grit Alpha: automated via sitemap (primary) and archive page (fallback)
        grit_posts = parse_grit_sitemap()
        if not grit_posts:
            grit_posts = parse_grit_archive()

        ideas = []
        for post in grit_posts:
            # Use URL slug as title if not available
            title = post.get("title") or fetch_post_title(post["url"])
            tickers = extract_tickers(title)
            for t in tickers:
                ideas.append({
                    "ticker": t,
                    "source": post["source"],
                    "title": title,
                    "url": post["url"],
                    "post_date": post.get("post_date"),
                })

        # Fiscal.ai: manual ingestion only (Vercel checkpoint blocks headless requests)
        fiscal_ideas = parse_fiscal_manual()
        ideas.extend(fiscal_ideas)

        persist_ideas(cur, ideas)

        added = 0
        for idea in ideas:
            if add_to_discovery(cur, idea["ticker"], idea["source"], idea["title"], idea["url"]):
                added += 1

        cur.execute("""
            UPDATE external_feed_ideas
            SET added_to_discovery = TRUE
            WHERE discovered_at = CURRENT_DATE
            AND added_to_discovery = FALSE
        """)

        conn.commit()
        path = write_obsidian(ideas)
        print(f"External Feed Parser: {len(ideas)} ticker ideas from {len(grit_posts)} Grit posts")
        print(f"Added to discovery_queue: {added}")
        print(f"Obsidian note: {path}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
