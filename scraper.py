#!/usr/bin/env python3
# ILANG: scraper.py | role:fetch | boundary:只抓公开页 不绕robots 不编数据
# Reads .ilang/site.ilang for provider list, fetches their promo/pricing pages,
# extracts deal info, writes data/offers.json. Pure stdlib.

import json
import os
import re
import urllib.request
import urllib.error
import urllib.robotparser
from html.parser import HTMLParser
from datetime import datetime, timezone
from html import unescape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ILANG_PATH = os.path.join(BASE_DIR, ".ilang", "site.ilang")
DATA_PATH = os.path.join(BASE_DIR, "data", "offers.json")

UA = "Mozilla/5.0 (compatible; VPSDealsBot/1.0; +https://vps-deals.pages.dev)"

# ---------------------------------------------------------------------------
# I-Lang parser: reads PROVIDERS module from site.ilang
# ---------------------------------------------------------------------------
def parse_ilang(path):
    """Parse .ilang/site.ilang and return config dict."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    config = {"providers": [], "brand": "", "niche": "", "domain": "", "locale": "en-US"}

    in_providers = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("::") and not stripped.startswith("  "):
            # Check for module/state headers
            if "PROVIDERS" in stripped and "title:" in stripped:
                in_providers = True
                continue
            elif stripped.startswith("::MODULE") and "PROVIDERS" not in stripped:
                in_providers = False
                continue
            elif stripped.startswith("::STATE") and "@SITE" in stripped:
                # Parse brand, niche, domain, locale
                for m in re.finditer(r'(\w+):([^,\s]+)', stripped):
                    key, val = m.group(1), m.group(2)
                    if key in ("brand", "niche", "domain", "locale"):
                        config[key] = val
                continue

        if in_providers and stripped and "|" in stripped:
            parts = [p.strip() for p in stripped.split("|")]
            if len(parts) >= 4:
                provider = {
                    "name": parts[0],
                    "homepage": parts[1],
                    "promo_page": parts[2],
                    "affiliate": parts[3].strip() if parts[3].strip() else None,
                }
                config["providers"].append(provider)

    return config

# ---------------------------------------------------------------------------
# HTTP fetch with robots.txt check
# ---------------------------------------------------------------------------
def check_robots(url):
    """Check robots.txt allows fetching this URL."""
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return True  # If robots.txt can't be read, assume allowed

def fetch(url):
    """Fetch URL content, return HTML text or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return None

# ---------------------------------------------------------------------------
# Deal extraction: regex-based parsing of pricing/promo pages
# ---------------------------------------------------------------------------
def extract_price(text):
    """Extract a price from text. Returns (value, currency) or (None, None)."""
    # Match patterns like $5.00, €4.50, £3.00, $5, 5.00/mo
    patterns = [
        (r'[\$]\s*(\d+(?:\.\d{1,2})?)\s*(?:/mo|/month|/m)?', 'USD'),
        (r'[\€]\s*(\d+(?:\.\d{1,2})?)\s*(?:/mo|/month|/m)?', 'EUR'),
        (r'[\£]\s*(\d+(?:\.\d{1,2})?)\s*(?:/mo|/month|/m)?', 'GBP'),
        (r'(\d+(?:\.\d{1,2})?)\s*(?:/mo|/month)', 'USD'),
    ]
    for pat, cur in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1), cur
    return None, None

def extract_deals(html, source_url, provider_name):
    """Extract deal entries from a provider's promo/pricing page."""
    deals = []
    if not html:
        return deals

    # Try to find pricing cards/tables - look for common patterns
    # Pattern 1: Look for elements with price-like content near plan names
    # We use a simple approach: find all text blocks that contain a price pattern
    # and extract surrounding context as the deal title

    # Remove scripts and styles
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL | re.IGNORECASE)

    # Find plan/price blocks - look for headings or divs with price
    # Common patterns: <h3>Plan Name</h3>...$5.00
    # Try to find structured pricing data

    # Extract from JSON-LD if present
    jsonld_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for m in re.finditer(jsonld_pattern, clean, flags=re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, dict):
                if data.get("@type") == "Product" and "offers" in data:
                    offers = data["offers"]
                    if isinstance(offers, dict):
                        offers = [offers]
                    for offer in offers:
                        deal = {
                            "title": f"{provider_name} - {data.get('name', 'Plan')}",
                            "provider": provider_name,
                            "source_url": source_url,
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        }
                        if "price" in offer:
                            deal["price"] = str(offer["price"])
                        if "priceCurrency" in offer:
                            deal["currency"] = offer["priceCurrency"]
                        if "url" in offer:
                            deal["offer_url"] = offer["url"]
                        elif "url" in data:
                            deal["offer_url"] = data["url"]
                        else:
                            deal["offer_url"] = source_url
                        if "priceValidUntil" in offer:
                            deal["valid_until"] = offer["priceValidUntil"]
                        deals.append(deal)
        except (json.JSONDecodeError, KeyError):
            pass

    # If no JSON-LD found, try regex extraction from pricing tables
    if not deals:
        # Find plan blocks: look for repeated patterns of plan name + price
        # Match div/section/article elements that contain both a heading and a price
        plan_blocks = re.findall(
            r'(?:<h[2-4][^>]*>(.*?)</h[2-4]>|<div[^>]*class=["\'][^"\']*(?:plan|price|card|tier)[^"\']*["\'][^>]*>(.*?)</div>)',
            clean, re.DOTALL | re.IGNORECASE
        )
        for block_group in plan_blocks:
            block_text = " ".join(t for t in block_group if t)
            if not block_text:
                continue
            # Strip tags
            plain = re.sub(r'<[^>]+>', ' ', block_text)
            plain = unescape(plain).strip()
            plain = re.sub(r'\s+', ' ', plain)
            if not plain or len(plain) > 200:
                continue
            price_val, currency = extract_price(plain)
            if price_val:
                deal = {
                    "title": f"{provider_name} - {plain[:100]}",
                    "provider": provider_name,
                    "price": price_val,
                    "currency": currency,
                    "offer_url": source_url,
                    "source_url": source_url,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
                deals.append(deal)

    # Last resort: extract first price found on page with a generic title
    if not deals:
        price_val, currency = extract_price(clean[:5000])
        if price_val:
            deal = {
                "title": f"{provider_name} VPS Plans",
                "provider": provider_name,
                "price": price_val,
                "currency": currency,
                "offer_url": source_url,
                "source_url": source_url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            deals.append(deal)

    # Deduplicate by title
    seen = set()
    unique = []
    for d in deals:
        if d["title"] not in seen:
            seen.add(d["title"])
            unique.append(d)

    return unique

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=== VPS Deals Scraper ===")
    config = parse_ilang(ILANG_PATH)
    print(f"Brand: {config['brand']}")
    print(f"Providers: {len(config['providers'])}")

    all_deals = []
    for prov in config["providers"]:
        print(f"\n--- {prov['name']} ---")
        print(f"  URL: {prov['promo_page']}")

        # Check robots.txt
        if not check_robots(prov["promo_page"]):
            print(f"  [SKIP] robots.txt disallows")
            continue

        html = fetch(prov["promo_page"])
        if not html:
            print(f"  [SKIP] fetch failed")
            continue

        deals = extract_deals(html, prov["promo_page"], prov["name"])
        print(f"  Found {len(deals)} deal(s)")

        # Apply affiliate link if configured
        for d in deals:
            if prov.get("affiliate"):
                d["offer_url"] = prov["affiliate"]

        all_deals.extend(deals)

    # Write offers.json
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(all_deals, f, indent=2, ensure_ascii=False)

    print(f"\n=== Done: {len(all_deals)} deals written to {DATA_PATH} ===")

if __name__ == "__main__":
    import urllib.parse  # needed for urlparse
    main()
