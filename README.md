# vps-deals-promo-radar

Zero-cost, zero-server, auto-updating VPS hosting deals aggregator. Pure Python, GitHub Actions cron, Cloudflare Pages.

## What it does

- `scraper.py` fetches each provider's public pricing/promo page, extracts deal title/price/currency/offer URL, writes `data/offers.json`
- `build.py` reads `offers.json`, renders static pages to `site/`, generates `sitemap.xml` + `robots.txt`
- GitHub Actions runs both every 6 hours, commits, and deploys to Cloudflare Pages
- Live at `vps-deals.pages.dev` (custom domain can be added)

## How to use

```bash
python scraper.py    # fetch deals → data/offers.json
python build.py      # render site → site/
```

Add or remove providers by editing `.ilang/site.ilang` — both scripts read that file for configuration.

## Project structure

```
.ilang/site.ilang          site rules (source of truth)
scraper.py                 fetcher
build.py                   renderer
templates/                 index, provider, deal, compare
data/offers.json           dataset
.github/workflows/update.yml   cron pipeline
site/                      build output (deployed)
```

## Tech stack

- Python 3 standard library only (urllib, html.parser, json, string, xml)
- No frameworks, no dependencies, no API keys
- GitHub Actions free tier (public repo, unlimited minutes)
- Cloudflare Pages free tier

## Monetization

- Affiliate links in deal pages (configured in `.ilang/site.ilang`)
- Exit: package domain + brand + revenue history for sale

## Site rules

Site rules are described in I-Lang protocol. See `.ilang/site.ilang`. Protocol info: ilang.ai
