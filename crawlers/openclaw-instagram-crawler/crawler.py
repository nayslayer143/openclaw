#!/usr/bin/env python3
"""OpenClaw Instagram Crawler — hashtag monitoring + finfluencer tracking for market signals."""
import argparse, json, logging, random, re, sys, time
from datetime import datetime
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
import config, storage, signals as sig

Path(config.LOG_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(Path(config.LOG_DIR) / f"crawler_{datetime.now():%Y%m%d}.log"),
              logging.StreamHandler(sys.stdout)])
log = logging.getLogger("instagram-crawler")

def _build_client():
    return httpx.Client(headers={"User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.5",
        "X-IG-App-ID": "936619743392459"}, follow_redirects=True, timeout=httpx.Timeout(30.0, connect=10.0))
def _polite_delay(): time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))
def _backoff_delay(a):
    d = min(config.BACKOFF_BASE_SEC * (2 ** a), config.BACKOFF_MAX_SEC); return d + random.uniform(0, d*0.25)
def _has_api_token(): return bool(config.INSTAGRAM_ACCESS_TOKEN)

def _graph_get(client, endpoint, params=None):
    url = f"{config.GRAPH_API_BASE}/{endpoint}"; p = params or {}; p["access_token"] = config.INSTAGRAM_ACCESS_TOKEN
    for a in range(config.MAX_RETRIES):
        try:
            resp = client.get(url, params=p)
            if resp.status_code == 200: return resp.json()
            elif resp.status_code == 429: time.sleep(_backoff_delay(a)); continue
            else: log.warning("Graph API HTTP %d: %s", resp.status_code, resp.text[:200]); return None
        except httpx.TimeoutException: log.warning("Graph API timeout (%d/%d)", a+1, config.MAX_RETRIES); time.sleep(_backoff_delay(a))
        except Exception as e: log.warning("Graph API error: %s", e); return None
    return None
def _make_post(item, author="", followers=0):
    return {"id": item.get("id",""), "caption": (item.get("caption") or "")[:config.MAX_CAPTION_CHARS],
        "likes": item.get("like_count",0), "comments": item.get("comments_count",0),
        "media_type": item.get("media_type","IMAGE").lower(), "url": item.get("permalink",""),
        "timestamp": item.get("timestamp",""), "author": author, "author_followers": followers}
def graph_fetch_hashtag_posts(client, hashtag):
    data = _graph_get(client, "ig_hashtag_search", {"q": hashtag})
    if not data or "data" not in data: return []
    results = data.get("data",[]); hid = results[0]["id"] if results else None
    if not hid: log.warning("Graph API: hashtag '%s' not found", hashtag); return []
    data = _graph_get(client, f"{hid}/recent_media",
        {"fields":"id,caption,like_count,comments_count,media_type,permalink,timestamp","limit":config.POSTS_PER_HASHTAG})
    if not data or "data" not in data: return []
    posts = [_make_post(i) for i in data.get("data",[])]
    log.info("  Graph API: %d posts for #%s", len(posts), hashtag); return posts
def graph_fetch_profile(client, username):
    data = _graph_get(client, "me", {"fields": f"business_discovery.username({username})"
        "{{username,name,biography,followers_count,media_count,media.limit(10)"
        "{{id,caption,like_count,comments_count,media_type,permalink,timestamp}}}}"})
    if not data or "business_discovery" not in data: return [], {}
    bd = data["business_discovery"]
    info = {"username":bd.get("username",username),"name":bd.get("name",""),"bio":bd.get("biography",""),
        "followers":bd.get("followers_count",0),"media_count":bd.get("media_count",0)}
    posts = [_make_post(i, username, info["followers"]) for i in bd.get("media",{}).get("data",[])]
    log.info("  Graph API: %d posts from @%s (%d followers)", len(posts), username, info["followers"])
    return posts, info
def _fetch_html(client, url):
    for a in range(config.MAX_RETRIES):
        try:
            resp = client.get(url)
            if resp.status_code == 200: return resp.text
            elif resp.status_code in (429,403):
                time.sleep(_backoff_delay(a + (1 if resp.status_code==403 else 0))); continue
            else: log.warning("HTTP %d for %s", resp.status_code, url); return None
        except httpx.TimeoutException: log.warning("Timeout %s (%d/%d)", url, a+1, config.MAX_RETRIES); time.sleep(_backoff_delay(a))
        except httpx.ConnectError as e: log.warning("Conn error %s: %s", url, e); return None
        except Exception as e: log.warning("Error %s: %s", url, e); return None
    return None
def _extract_json_obj(text, start):
    brace = text.find("{", start)
    if brace == -1: return None
    depth, end = 0, brace
    for i in range(brace, min(brace+200000, len(text))):
        if text[i] == "{": depth += 1
        elif text[i] == "}": depth -= 1
        if depth == 0: end = i+1; break
    try: return json.loads(text[brace:end])
    except (json.JSONDecodeError, TypeError): return None
_TN = {"GraphImage":"image","GraphVideo":"video","GraphSidecar":"carousel"}
def _node_to_post(node, author=""):
    ce = node.get("edge_media_to_caption",{}).get("edges",[]); cap = ce[0]["node"]["text"] if ce else ""
    sc = node.get("shortcode", node.get("id",""))
    return {"id":sc,"caption":cap[:config.MAX_CAPTION_CHARS],
        "likes":node.get("edge_liked_by",{}).get("count",0),"comments":node.get("edge_media_to_comment",{}).get("count",0),
        "media_type":_TN.get(node.get("__typename",""),"image"),"url":f"{config.BASE_URL}/p/{sc}/",
        "timestamp":str(node.get("taken_at_timestamp","")),"author":author or node.get("owner",{}).get("username",""),"author_followers":0}
def scrape_hashtag_page(client, hashtag):
    url = config.HASHTAG_URL.format(hashtag=hashtag); log.info("Scraping: %s", url)
    html = _fetch_html(client, url); return _parse_hashtag_html(html, hashtag) if html else []
def _parse_hashtag_html(html, hashtag):
    try: soup = BeautifulSoup(html, "html.parser")
    except Exception: return []
    for fn in (_try_shared_data, _try_script_json, _try_meta_tags):
        posts = fn(soup, hashtag)
        if posts: return posts
    return []
def _try_shared_data(soup, hashtag):
    for script in soup.select("script"):
        text = script.string or ""
        if "window._sharedData" not in text and "window.__additionalDataLoaded" not in text: continue
        for marker in ["window._sharedData = ","window.__additionalDataLoaded("]:
            idx = text.find(marker)
            if idx == -1: continue
            start = idx + len(marker)
            if marker.endswith("("): comma = text.find(",",start); start = comma+1 if comma!=-1 else start
            data = _extract_json_obj(text, start)
            if not data: continue
            posts = _extract_from_shared(data)
            if posts: return posts
    return []
def _extract_from_shared(data):
    posts = []
    try:
        pages = data.get("entry_data",{}).get("TagPage",[]) or ([data] if "graphql" in data else [])
        for page in pages:
            ht = page.get("graphql",{}).get("hashtag",{}) or page.get("data",{}).get("hashtag",{})
            if not ht: continue
            edges = ht.get("edge_hashtag_to_media",{}).get("edges",[]) or ht.get("edge_hashtag_to_top_posts",{}).get("edges",[])
            for e in edges[:config.POSTS_PER_HASHTAG]: posts.append(_node_to_post(e.get("node",{})))
    except (KeyError,TypeError,IndexError): pass
    return posts
def _try_script_json(soup, hashtag):
    posts = []
    for s in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(s.string or "")
            if isinstance(data,dict) and "mainEntity" in data:
                for item in data.get("mainEntity",{}).get("itemListElement",[]):
                    url = item.get("url",""); sc = url.rstrip("/").split("/")[-1] if "/p/" in url else ""
                    posts.append({"id":sc or f"ig-{hash(url)&0xFFFFFFFF:08x}","caption":item.get("description","")[:config.MAX_CAPTION_CHARS],
                        "likes":0,"comments":0,"media_type":"image","url":url,"timestamp":"","author":"","author_followers":0})
        except (json.JSONDecodeError,TypeError): continue
    return posts[:config.POSTS_PER_HASHTAG]
def _try_meta_tags(soup, hashtag):
    posts = []
    for a in soup.select("a[href*='/p/']")[:config.POSTS_PER_HASHTAG]:
        href = a.get("href",""); sc = href.strip("/").split("/")[-1] if "/p/" in href else ""
        if not sc: continue
        img = a.select_one("img"); alt = (img.get("alt","") if img else "")[:config.MAX_CAPTION_CHARS]
        posts.append({"id":sc,"caption":alt,"likes":0,"comments":0,"media_type":"image",
            "url":f"{config.BASE_URL}/p/{sc}/","timestamp":"","author":"","author_followers":0})
    return posts

def _parse_count(text):
    text = text.replace(",","").strip(); mult = 1
    if text.endswith(("K","k")): mult=1000; text=text[:-1]
    elif text.endswith(("M","m")): mult=1_000_000; text=text[:-1]
    try: return int(float(text)*mult)
    except ValueError: return 0

def scrape_profile_page(client, username):
    url = config.PROFILE_URL.format(username=username); log.info("Scraping profile: %s", url)
    html = _fetch_html(client, url); return _parse_profile_html(html, username) if html else ([], {})

def _parse_profile_html(html, username):
    posts=[]; info={"username":username,"name":"","bio":"","followers":0,"media_count":0}
    try: soup = BeautifulSoup(html, "html.parser")
    except Exception: return posts, info
    meta = soup.select_one("meta[property='og:description']")
    if meta:
        desc = meta.get("content","")
        fm = re.search(r"([\d,.]+[KMkm]?)\s*Followers", desc)
        if fm: info["followers"] = _parse_count(fm.group(1))
        pm = re.search(r"([\d,.]+[KMkm]?)\s*Posts", desc)
        if pm: info["media_count"] = _parse_count(pm.group(1))
    for script in soup.select("script"):
        text = script.string or ""
        if "window._sharedData" not in text: continue
        idx = text.find("window._sharedData = ")
        if idx == -1: continue
        data = _extract_json_obj(text, idx+len("window._sharedData = "))
        if not data: continue
        try:
            for page in data.get("entry_data",{}).get("ProfilePage",[]):
                user = page.get("graphql",{}).get("user",{})
                if not user: continue
                info["name"]=user.get("full_name",""); info["bio"]=user.get("biography","")
                info["followers"]=user.get("edge_followed_by",{}).get("count",0)
                for edge in user.get("edge_owner_to_timeline_media",{}).get("edges",[])[:config.POSTS_PER_HASHTAG]:
                    p = _node_to_post(edge.get("node",{}), author=username); p["author_followers"]=info["followers"]; posts.append(p)
        except (json.JSONDecodeError,TypeError,KeyError): continue
    if not posts:
        for a in soup.select("a[href*='/p/']")[:config.POSTS_PER_HASHTAG]:
            href=a.get("href",""); sc=href.strip("/").split("/")[-1] if "/p/" in href else ""
            if sc: posts.append({"id":sc,"caption":"","likes":0,"comments":0,"media_type":"image",
                "url":f"{config.BASE_URL}/p/{sc}/","timestamp":"","author":username,"author_followers":info["followers"]})
    return posts, info

def fetch_hashtag(client, ht):
    return graph_fetch_hashtag_posts(client, ht) if _has_api_token() else scrape_hashtag_page(client, ht)
def fetch_profile(client, u):
    return graph_fetch_profile(client, u) if _has_api_token() else scrape_profile_page(client, u)

def crawl_hashtags(client, hashtags):
    sigs = []
    for ht in hashtags:
        for p in fetch_hashtag(client, ht): sigs.append(sig.build_signal(p, platform=config.PLATFORM, hashtag=ht))
        _polite_delay()
    return sigs
def crawl_influencers(client, usernames):
    sigs, profiles = [], {}
    for u in usernames:
        posts, info = fetch_profile(client, u); profiles[u] = info
        for p in posts: sigs.append(sig.build_signal(p, platform=config.PLATFORM))
        _polite_delay()
    return sigs, profiles

def _ratio_bar(bull, bear, w=30):
    total=bull+bear
    if total==0: return "["+"."*w+"]"
    bw=round(bull/total*w); return "["+"#"*bw+"-"*(w-bw)+"]"
def print_dashboard(sigs):
    agg = sig.aggregate_hashtag_sentiment(sigs)
    if not agg: print("\nNo signals found."); return
    print(f"\n{'='*68}\n  INSTAGRAM SENTIMENT — {datetime.now():%Y-%m-%d %H:%M}\n{'='*68}")
    for tk, d in sorted(agg.items(), key=lambda x: x[1]["total"], reverse=True)[:20]:
        label = f"#{tk}" if not tk.startswith("$") else tk
        print(f"\n  {label:16s}  posts={d['total']:3d}  conf={d['avg_confidence']:.2f}  "
              f"likes={d['total_likes']:5d}  b/b={d['bull_bear_ratio']:.1f}")
        print(f"    bull={d['bullish']:3d} {_ratio_bar(d['bullish'], d['bearish'])}")
    print(f"\n{'='*68}\n")
def print_influencer_report(sigs, profiles):
    if not profiles: print("\nNo influencer data found."); return
    print(f"\n{'='*68}\n  INFLUENCER ACTIVITY — {datetime.now():%Y-%m-%d %H:%M}\n{'='*68}")
    for u, info in profiles.items():
        usigs = [s for s in sigs if s.get("source_author")==u]
        print(f"\n  @{u:20s}  followers={info.get('followers',0):>8,}")
        for s in usigs[:5]:
            print(f"    [{s.get('direction','?'):7s}] ({s.get('engagement',{}).get('upvotes',0):>5} likes) {s.get('body','')[:70]}")
    print(f"\n{'='*68}\n")
def print_hashtag_detail(sigs, hashtag):
    rel = [s for s in sigs if s.get("ticker_or_market")==hashtag or hashtag in str(s.get("tags",[]))]
    if not rel: print(f"\nNo signals found for #{hashtag}"); return
    d = sig.aggregate_hashtag_sentiment(rel).get(hashtag, {})
    print(f"\n{'='*48}\n  #{hashtag} — SENTIMENT\n{'='*48}")
    for k in ["total","bullish","bearish","neutral"]: print(f"  {k:15s}: {d.get(k,0)}")
    print(f"  {'avg_confidence':15s}: {d.get('avg_confidence',0):.2f}")
    print(f"  {'bull/bear ratio':15s}: {d.get('bull_bear_ratio',0):.2f}")
    print(f"  velocity: {sig.compute_velocity(rel).get(hashtag,len(rel))} posts this poll")
    for s in sorted(rel, key=lambda s: s.get("engagement",{}).get("upvotes",0), reverse=True)[:5]:
        print(f"    [{s.get('direction','?'):7s}] ({s.get('engagement',{}).get('upvotes',0)} likes) {s.get('body','')[:80]}")
    print(f"{'='*48}\n")

def monitor_loop(client):
    log.info("Starting monitor (%s, Ctrl+C to stop)...", "Graph API" if _has_api_token() else "HTML scraping")
    log.info("Watching hashtags: %s", ", ".join(config.HASHTAGS))
    last_ht=last_prof=0; cycle=0
    try:
        while True:
            cycle+=1; now=time.time(); crawl_id=f"instagram-{datetime.now():%Y%m%d%H%M%S}-{cycle}"; batch=[]
            if now-last_ht >= config.HASHTAG_INTERVAL_SEC:
                log.info("=== Hashtag crawl (cycle %d) ===", cycle); batch.extend(crawl_hashtags(client, config.HASHTAGS)); last_ht=now
            if now-last_prof >= config.PROFILE_INTERVAL_SEC:
                log.info("=== Influencer scan (cycle %d) ===", cycle)
                inf,_ = crawl_influencers(client, config.INFLUENCERS); batch.extend(inf); last_prof=now
            if batch: storage.write_signals(config.PLATFORM, crawl_id, batch); log.info("Wrote %d signals", len(batch)); storage.cleanup()
            time.sleep(min(config.HASHTAG_INTERVAL_SEC, config.PROFILE_INTERVAL_SEC)/2)
    except KeyboardInterrupt: log.info("Monitor stopped.")

def build_parser():
    p = argparse.ArgumentParser(description="OpenClaw Instagram Crawler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python crawler.py                        # start monitoring hashtags\n"
               "  python crawler.py --hashtag crypto       # track specific hashtag\n"
               "  python crawler.py --influencers          # top finfluencer activity\n"
               "  python crawler.py --once                 # single pass\n")
    p.add_argument("--hashtag", "-t", help="Track a specific hashtag")
    p.add_argument("--influencers", action="store_true", help="Crawl tracked finfluencer profiles")
    p.add_argument("--once", action="store_true", help="One crawl cycle then exit")
    return p

def main():
    args = build_parser().parse_args(); storage.init(); client = _build_client()
    crawl_id = f"instagram-{datetime.now():%Y%m%d%H%M%S}"
    log.info("Mode: %s", "Graph API" if _has_api_token() else "HTML scraping fallback")
    try:
        if args.hashtag:
            ht = args.hashtag.lower().strip("#"); log.info("Tracking #%s...", ht)
            sl = [sig.build_signal(p, platform=config.PLATFORM, hashtag=ht) for p in fetch_hashtag(client, ht)]
            if sl: storage.write_signals(config.PLATFORM, crawl_id, sl)
            print_hashtag_detail(sl, ht)
        elif args.influencers:
            sl, profiles = crawl_influencers(client, config.INFLUENCERS)
            if sl: storage.write_signals(config.PLATFORM, crawl_id, sl)
            print_influencer_report(sl, profiles)
        elif args.once:
            log.info("Single crawl cycle..."); batch = crawl_hashtags(client, config.HASHTAGS)
            inf,_ = crawl_influencers(client, config.INFLUENCERS); batch.extend(inf)
            if batch: storage.write_signals(config.PLATFORM, crawl_id, batch); print_dashboard(batch)
            log.info("Single cycle: %d signals", len(batch))
        else: monitor_loop(client)
    finally: client.close()

if __name__ == "__main__": main()
