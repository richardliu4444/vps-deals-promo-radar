#!/usr/bin/env python3
# ILANG: build.py | role:render | boundary:只渲染真实数据 不编内容
# Reads .ilang/site.ilang for config + data/offers.json for data,
# renders templates to site/, generates sitemap.xml + robots.txt. Pure stdlib.

import json
import os
import re
import html
from datetime import datetime, timezone
from string import Template

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ILANG_PATH = os.path.join(BASE_DIR, ".ilang", "site.ilang")
DATA_PATH = os.path.join(BASE_DIR, "data", "offers.json")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
SITE_DIR = os.path.join(BASE_DIR, "site")

# ---------------------------------------------------------------------------
# I-Lang parser (same logic as scraper.py, kept standalone for zero-coupling)
# ---------------------------------------------------------------------------
def parse_ilang(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    config = {"providers": [], "brand": "vps-deals", "niche": "VPS", "domain": "vps-deals.pages.dev", "locale": "en-US"}

    in_providers = False
    for line in lines:
        stripped = line.strip()
        if "PROVIDERS" in stripped and "title:" in stripped:
            in_providers = True
            continue
        elif stripped.startswith("::MODULE") and "PROVIDERS" not in stripped:
            in_providers = False
            continue
        elif stripped.startswith("::STATE") and "@SITE" in stripped:
            for m in re.finditer(r'(\w+):([^,\s]+)', stripped):
                key, val = m.group(1), m.group(2)
                if key in ("brand", "niche", "domain", "locale"):
                    config[key] = val
            continue

        if in_providers and stripped and "|" in stripped:
            parts = [p.strip() for p in stripped.split("|")]
            if len(parts) >= 4:
                config["providers"].append({
                    "name": parts[0],
                    "homepage": parts[1],
                    "promo_page": parts[2],
                    "affiliate": parts[3].strip() if parts[3].strip() else None,
                })

    return config

# ---------------------------------------------------------------------------
# Simple template engine: replaces {{var}} placeholders
# ---------------------------------------------------------------------------
def render(template_str, context):
    """Replace {{key}} with context[key]. Supports nested dict access via dot."""
    def replacer(m):
        key = m.group(1).strip()
        # Try direct lookup
        if key in context:
            val = context[key]
            return str(val) if val is not None else ""
        # Try dot notation (e.g., deal.price)
        parts = key.split(".")
        val = context
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return ""
        return str(val) if val is not None else ""
    return re.sub(r'\{\{(\w+(?:\.\w+)*)\}\}', replacer, template_str)

def render_loop(template_str, items, item_key="item"):
    """Render {{#loop items}}...{{/loop}} blocks."""
    def loop_replacer(m):
        block = m.group(2)
        var_name = m.group(1).strip()
        result = []
        for i, item in enumerate(items):
            ctx = {item_key: item, "index": i}
            result.append(render(block, {item_key: item, "index": str(i)}))
        return "".join(result)
    return re.sub(r'\{\{#loop\s+(\w+)\}\}(.*?)\{\{/loop\}\}', loop_replacer, template_str, flags=re.DOTALL)

# ---------------------------------------------------------------------------
# JSON-LD generators
# ---------------------------------------------------------------------------
def make_offer_jsonld(deal, domain):
    d = {"@type": "Offer"}
    if deal.get("price"):
        d["price"] = deal["price"]
    if deal.get("currency"):
        d["priceCurrency"] = deal["currency"]
    d["availability"] = "https://schema.org/InStock"
    if deal.get("valid_until"):
        d["priceValidUntil"] = deal["valid_until"]
    d["url"] = f"https://{domain}/deal-{deal['id']}.html"
    return d

def make_breadcrumb_jsonld(crumbs):
    items = []
    for i, (name, url) in enumerate(crumbs, 1):
        items.append({"@type": "ListItem", "position": i, "name": name, "item": url})
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}

def make_itemlist_jsonld(deals, domain):
    items = []
    for i, d in enumerate(deals, 1):
        items.append({"@type": "ListItem", "position": i, "url": f"https://{domain}/deal-{d['id']}.html", "name": d["title"]})
    return {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": items}

def make_product_jsonld(provider_name, deals, domain):
    offers = [make_offer_jsonld(d, domain) for d in deals if d.get("price")]
    if not offers:
        return None
    prices = [float(o["price"]) for o in offers if o.get("price")]
    obj = {"@context": "https://schema.org", "@type": "Product", "name": f"{provider_name} VPS Plans"}
    if len(prices) >= 2:
        obj["offers"] = {"@type": "AggregateOffer", "lowPrice": str(min(prices)), "highPrice": str(max(prices)), "offerCount": len(offers), "priceCurrency": offers[0].get("priceCurrency", "USD")}
    else:
        obj["offers"] = offers[0]
    return obj

# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------
def slugify(text):
    text = re.sub(r'[^\w\s-]', '', text.lower()).strip()
    return re.sub(r'[-\s]+', '-', text)

# ---------------------------------------------------------------------------
# Load templates
# ---------------------------------------------------------------------------
def load_template(name):
    path = os.path.join(TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------
def main():
    print("=== VPS Deals Build ===")
    config = parse_ilang(ILANG_PATH)
    domain = config["domain"]
    brand = config["brand"]
    print(f"Brand: {brand}, Domain: {domain}")

    # Load offers
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        offers = json.load(f)
    print(f"Offers: {len(offers)}")

    # Assign IDs
    for i, deal in enumerate(offers):
        deal["id"] = i + 1
        deal["slug"] = slugify(deal["title"])[:60]

    # Group by provider
    by_provider = {}
    for d in offers:
        by_provider.setdefault(d["provider"], []).append(d)

    # Sort offers by price ascending (cheapest first)
    def sort_key(d):
        try:
            return float(d.get("price", "999999"))
        except (ValueError, TypeError):
            return 999999.0
    offers_sorted = sorted(offers, key=sort_key)

    # Load templates
    tpl_index = load_template("index.html")
    tpl_provider = load_template("provider.html")
    tpl_deal = load_template("deal.html")
    tpl_compare = load_template("compare.html")

    os.makedirs(SITE_DIR, exist_ok=True)

    # 1. Index page
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    itemlist_jsonld = json.dumps(make_itemlist_jsonld(offers, domain), indent=2)
    index_html = render(tpl_index, {
        "brand": brand,
        "domain": domain,
        "generated": now_str,
        "itemlist_jsonld": itemlist_jsonld,
        "total_deals": str(len(offers)),
    })
    # Render deal loop
    deal_cards = []
    for d in offers_sorted:
        card = render('''
        <a href="deal-{{id}}.html" class="card">
            <div class="card-provider">{{provider}}</div>
            <div class="card-title">{{title_short}}</div>
            <div class="card-price">{{price_display}}</div>
        </a>''', {
            "id": d["id"],
            "provider": d.get("provider", ""),
            "title_short": d["title"][:80],
            "price_display": f"{d.get('currency_symbol','')}{d.get('price','?')}" if d.get("price") else "Price N/A",
        })
        deal_cards.append(card)
    index_html = index_html.replace("{{DEAL_CARDS}}", "\n".join(deal_cards))

    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print("  -> index.html")

    # 2. Provider pages
    for prov_name, prov_deals in by_provider.items():
        slug = slugify(prov_name)
        product_jsonld = make_product_jsonld(prov_name, prov_deals, domain)
        breadcrumb = make_breadcrumb_jsonld([
            ("Home", f"https://{domain}/index.html"),
            (prov_name, f"https://{domain}/provider-{slug}.html"),
        ])
        prov_html = render(tpl_provider, {
            "brand": brand,
            "domain": domain,
            "provider_name": prov_name,
            "generated": now_str,
            "product_jsonld": json.dumps(product_jsonld, indent=2) if product_jsonld else "",
            "breadcrumb_jsonld": json.dumps(breadcrumb, indent=2),
        })
        # Render deal rows
        rows = []
        for d in prov_deals:
            row = render('<tr><td><a href="deal-{{id}}.html">{{title}}</a></td><td>{{price_display}}</td><td>{{currency}}</td></tr>', {
                "id": d["id"],
                "title": d["title"],
                "price_display": d.get("price", "N/A"),
                "currency": d.get("currency", ""),
            })
            rows.append(row)
        prov_html = prov_html.replace("{{DEAL_ROWS}}", "\n".join(rows))

        with open(os.path.join(SITE_DIR, f"provider-{slug}.html"), "w", encoding="utf-8") as f:
            f.write(prov_html)
        print(f"  -> provider-{slug}.html")

    # 3. Deal detail pages
    for d in offers:
        offer_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "Offer",
            **{k: v for k, v in make_offer_jsonld(d, domain).items() if k != "@type"}
        }, indent=2)
        breadcrumb = make_breadcrumb_jsonld([
            ("Home", f"https://{domain}/index.html"),
            (d["provider"], f"https://{domain}/provider-{slugify(d['provider'])}.html"),
            (d["title"][:50], f"https://{domain}/deal-{d['id']}.html"),
        ])
        deal_html = render(tpl_deal, {
            "brand": brand,
            "domain": domain,
            "deal_title": d["title"],
            "provider": d.get("provider", ""),
            "price": d.get("price", "Not listed"),
            "currency": d.get("currency", ""),
            "offer_url": d.get("offer_url", d.get("source_url", "")),
            "source_url": d.get("source_url", ""),
            "fetched_at": d.get("fetched_at", ""),
            "valid_until": d.get("valid_until", "Not specified"),
            "deal_id": str(d["id"]),
            "generated": now_str,
            "offer_jsonld": offer_jsonld,
            "breadcrumb_jsonld": json.dumps(breadcrumb, indent=2),
        })
        with open(os.path.join(SITE_DIR, f"deal-{d['id']}.html"), "w", encoding="utf-8") as f:
            f.write(deal_html)
    print(f"  -> {len(offers)} deal pages")

    # 4. Compare page
    compare_html = render(tpl_compare, {
        "brand": brand,
        "domain": domain,
        "generated": now_str,
        "itemlist_jsonld": json.dumps(make_itemlist_jsonld(offers_sorted, domain), indent=2),
    })
    # Render compare rows
    comp_rows = []
    for d in offers_sorted:
        row = render('<tr><td>{{provider}}</td><td><a href="deal-{{id}}.html">{{title}}</a></td><td>{{price}}</td><td>{{currency}}</td><td><a href="{{offer_url}}" rel="nofollow noopener">Visit</a></td></tr>', {
            "provider": d.get("provider", ""),
            "id": d["id"],
            "title": d["title"][:60],
            "price": d.get("price", "N/A"),
            "currency": d.get("currency", ""),
            "offer_url": d.get("offer_url", d.get("source_url", "#")),
        })
        comp_rows.append(row)
    compare_html = compare_html.replace("{{COMPARE_ROWS}}", "\n".join(comp_rows))

    with open(os.path.join(SITE_DIR, "compare.html"), "w", encoding="utf-8") as f:
        f.write(compare_html)
    print("  -> compare.html")

    # 5. Sitemap
    sitemap_urls = [f"https://{domain}/"]
    sitemap_urls.append(f"https://{domain}/compare.html")
    for prov_name in by_provider:
        sitemap_urls.append(f"https://{domain}/provider-{slugify(prov_name)}.html")
    for d in offers:
        sitemap_urls.append(f"https://{domain}/deal-{d['id']}.html")

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in sitemap_urls:
        sitemap_xml += f"  <url><loc>{url}</loc><lastmod>{now_str}</lastmod></url>\n"
    sitemap_xml += '</urlset>\n'
    with open(os.path.join(SITE_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print("  -> sitemap.xml")

    # 6. Robots.txt
    robots_txt = f"User-agent: *\nAllow: /\n\nSitemap: https://{domain}/sitemap.xml\n"
    with open(os.path.join(SITE_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots_txt)
    print("  -> robots.txt")

    print(f"\n=== Build complete: {len(offers)} deals, {len(by_provider)} providers ===")

if __name__ == "__main__":
    main()
