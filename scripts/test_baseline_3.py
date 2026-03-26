#!/usr/bin/env python3
"""
test_baseline_3.py — Parallel price scraper for 3 e-commerce sites.

Scrapes product names + prices from 3 shops simultaneously using
threading + the OpenClaw BrowserPool, then prints a comparison table.

Sites:
  - https://shop1.example.com/products
  - https://shop2.example.com/products
  - https://shop3.example.com/products

Speed strategy:
  - One BrowserContext, three tabs — avoids 3x browser launch overhead.
  - All three navigations run concurrently via threading.
  - DOM extraction (not screenshot) — fastest content mode for text.
  - wait_until="domcontentloaded" — doesn't wait for images/fonts/XHR.
  - rate_limit_seconds patched to (0, 0) — removes artificial delays
    since these are the same-task target sites, not a crawl.
"""
from __future__ import annotations

import sys
import re
import threading
import time
from typing import Optional

# Make the browser package importable from any working directory.
sys.path.insert(0, "/Users/nayslayer/openclaw/scripts")

from browser.browser_engine import BrowserEngine
from browser.eyes import Eyes

# ── Target sites ─────────────────────────────────────────────────────────────

SITES = [
    "https://shop1.example.com/products",
    "https://shop2.example.com/products",
    "https://shop3.example.com/products",
]

# ── Price extraction helpers ──────────────────────────────────────────────────

# Matches common price formats: $12.99, €9, £1,299.00, 45.00 USD, etc.
_PRICE_RE = re.compile(
    r"""
    (?:                         # optional currency symbol before
        [\$\€\£\¥\₹]
    )?
    \d{1,6}                     # integer part
    (?:[,\.\s]\d{2,3})*         # optional thousands / decimal
    (?:\.\d{2})?                # optional cent part
    \s*                         # optional space
    (?:USD|EUR|GBP|CAD|AUD)?    # optional trailing ISO code
    """,
    re.VERBOSE,
)


def _extract_products_js(page) -> list[dict]:
    """
    Try to extract structured product data via JavaScript first.

    Looks for common e-commerce HTML patterns (schema.org microdata,
    data attributes, class names). Falls back gracefully to empty list
    so the text-parse path can take over.
    """
    js = """
    (() => {
        const results = [];

        // Strategy 1: schema.org Product microdata
        document.querySelectorAll('[itemtype*="Product"]').forEach(el => {
            const name = el.querySelector('[itemprop="name"]');
            const price = el.querySelector('[itemprop="price"]');
            if (name && price) {
                results.push({
                    name: name.textContent.trim(),
                    price: (price.getAttribute('content') || price.textContent).trim()
                });
            }
        });
        if (results.length > 0) return results;

        // Strategy 2: common product card class names
        const cardSelectors = [
            '.product-card', '.product-item', '.product',
            '[class*="product"]', '[data-product-id]'
        ];
        for (const sel of cardSelectors) {
            const cards = document.querySelectorAll(sel);
            if (cards.length === 0) continue;
            cards.forEach(card => {
                const nameEl = card.querySelector(
                    'h1,h2,h3,h4,.product-name,.product-title,[class*="name"],[class*="title"]'
                );
                const priceEl = card.querySelector(
                    '.price,[class*="price"],[data-price],[itemprop="price"]'
                );
                if (nameEl || priceEl) {
                    results.push({
                        name: nameEl ? nameEl.textContent.trim() : '(unknown)',
                        price: priceEl ? priceEl.textContent.trim() : '(unknown)'
                    });
                }
            });
            if (results.length > 0) return results;
        }

        return results;
    })();
    """
    try:
        return page.evaluate(js) or []
    except Exception:
        return []


def _parse_products_from_text(text: str) -> list[dict]:
    """
    Fallback: scan raw DOM text for name/price pairs.

    Heuristic: lines containing a price pattern are candidates.
    The line immediately above a price line is treated as the product name.
    Works for most flat product list layouts.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    products = []
    for i, line in enumerate(lines):
        if _PRICE_RE.search(line):
            name = lines[i - 1] if i > 0 else "(unknown)"
            # Skip if 'name' looks like navigation/header noise
            if len(name) < 3 or name.lower() in {"home", "products", "shop", "menu"}:
                name = "(unknown)"
            products.append({"name": name, "price": line})
    return products


# ── Per-tab scrape function ───────────────────────────────────────────────────

def scrape_site(
    context,                  # Playwright BrowserContext
    url: str,
    results: dict,            # shared dict keyed by url
    errors: dict,
):
    """
    Open a new tab in the shared context, navigate to url,
    extract products, write into results[url].
    """
    page = None
    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Try structured JS extraction first (fastest + most accurate)
        products = _extract_products_js(page)

        if not products:
            # Fallback: pull DOM text and parse heuristically
            eyes = Eyes.__new__(Eyes)
            eyes._page = page
            text = page.locator("body").inner_text()
            products = _parse_products_from_text(text)

        results[url] = products

    except Exception as exc:
        errors[url] = str(exc)
        results[url] = []
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


# ── Comparison table printer ──────────────────────────────────────────────────

def _site_label(url: str) -> str:
    """Turn a URL into a short column header, e.g. 'shop1.example.com'."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return url


def print_comparison_table(results: dict[str, list[dict]], errors: dict[str, str]):
    """
    Print a side-by-side comparison table.

    Layout: each site gets its own column with NAME | PRICE pairs.
    If all sites share identical product names, a single Name column is shown.
    Otherwise each site column shows name + price together.
    """
    labels = [_site_label(u) for u in SITES]
    site_data = [results.get(u, []) for u in SITES]

    # ── Error summary ──
    if errors:
        print("\n[ERRORS]")
        for url, msg in errors.items():
            print(f"  {_site_label(url)}: {msg}")

    # ── Determine max rows ──
    max_rows = max((len(d) for d in site_data), default=0)
    if max_rows == 0:
        print("\nNo products extracted from any site.")
        return

    # ── Column widths ──
    col_w = 34  # chars per site column
    sep = " | "

    header = sep.join(f"{lbl:<{col_w}}" for lbl in labels)
    divider = "-+-".join("-" * col_w for _ in labels)

    print()
    print("PRODUCT PRICE COMPARISON")
    print("=" * len(header))
    print(header)
    print(divider)

    for i in range(max_rows):
        row_parts = []
        for data in site_data:
            if i < len(data):
                name = data[i].get("name", "")[:18].strip()
                price = data[i].get("price", "")[:13].strip()
                cell = f"{name:<18} {price:>13}"
            else:
                cell = " " * col_w
            row_parts.append(f"{cell:<{col_w}}")
        print(sep.join(row_parts))

    print(divider)
    counts = "  |  ".join(
        f"{lbl}: {len(d)} products" for lbl, d in zip(labels, site_data)
    )
    print(f"\nCounts — {counts}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t_start = time.perf_counter()

    # One browser launch, three tabs — maximises reuse, minimises overhead.
    # rate_limit_seconds=(0,0) skips artificial inter-request delay since
    # all three requests are to different hosts and run in parallel anyway.
    with BrowserEngine(
        headless=True,
        rate_limit_seconds=(0, 0),   # no delay — parallel tabs, distinct domains
    ) as engine:
        context = engine._context    # access the Playwright context directly

        results: dict[str, list[dict]] = {}
        errors: dict[str, str] = {}

        # Launch one thread per site — all three tabs navigate simultaneously.
        threads = [
            threading.Thread(
                target=scrape_site,
                args=(context, url, results, errors),
                daemon=True,
            )
            for url in SITES
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=40)   # hard ceiling per site: 40 s

    t_elapsed = time.perf_counter() - t_start
    print_comparison_table(results, errors)
    print(f"\nTotal wall time: {t_elapsed:.2f}s")


if __name__ == "__main__":
    main()
