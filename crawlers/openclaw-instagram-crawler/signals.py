"""Signal extraction and normalization for Instagram posts."""
import re, hashlib, uuid
from datetime import datetime, timezone

CASHTAG_RE = re.compile(r"\$([A-Z]{1,6}(?:\.[A-Z])?)(?:\s|$|[,.\-!?;:#])")
TICKER_BLACKLIST = {"I","A","IT","IS","AM","PM","CEO","IPO","ATH","ATL","DD","TA","IMO","TLDR",
    "YOLO","HODL","FOMO","FUD","USD","EUR","GBP","THE","FOR","AND","NOT","BUT","ALL","HAS","ARE","WAS","DM","IG","BIO","LINK"}
BULLISH_WORDS = {"bullish","moon","mooning","pump","pumping","rocket","calls","long","buy","buying",
    "accumulate","undervalued","breakout","rally","rip","send it","ath","green","diamond hands","tendies","squeeze","to the moon","upside","bull run","going up","lambo"}
BEARISH_WORDS = {"bearish","dump","dumping","crash","crashing","rug","puts","short","sell","selling",
    "overvalued","bubble","breakdown","correction","dip","red","paper hands","bagholding","rugpull","rug pull","downside","dead cat","bear market","going down","scam"}
REALTIME_WORDS = {"breaking","just now","right now","happening","live"}
HOURS_WORDS = {"today","tonight","expiry","0dte","this morning"}
CONTENT_KEYWORDS = {
    "educational": {"learn","explained","guide","tutorial","how to","strategy","tip","lesson","fundamentals"},
    "hype": {"moon","rocket","lambo","100x","1000x","generational","dont miss","last chance","hurry"},
    "news": {"breaking","announcement","just in","report","sec","fed","regulation","approved","listing"},
    "analysis": {"chart","technical","support","resistance","fibonacci","rsi","macd","volume","pattern","trend"}}

def extract_tickers(text):
    if not text: return []
    return list(dict.fromkeys(t for t in CASHTAG_RE.findall(text + " ") if t not in TICKER_BLACKLIST))

def score_sentiment(text):
    if not text: return "unknown", 0.0
    lower = text.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in lower); bear = sum(1 for w in BEARISH_WORDS if w in lower)
    total = bull + bear
    if total == 0: return "neutral", 0.1
    ratio = bull / total
    if ratio > 0.65: return "bullish", round(min(0.5 + bull * 0.05, 0.95), 2)
    if ratio < 0.35: return "bearish", round(min(0.5 + bear * 0.05, 0.95), 2)
    return "neutral", 0.3

def classify_content(text):
    if not text: return "unknown"
    lower = text.lower()
    scores = {ct: sum(1 for w in kw if w in lower) for ct, kw in CONTENT_KEYWORDS.items()}
    best = max(scores, key=scores.get); return best if scores[best] > 0 else "general"

def detect_urgency(text):
    if not text: return "days"
    lower = text.lower()
    if any(w in lower for w in REALTIME_WORDS): return "realtime"
    if any(w in lower for w in HOURS_WORDS): return "hours"
    return "days"

def make_signal_id(platform, source_id):
    return hashlib.sha256(f"{platform}:{source_id}".encode()).hexdigest()[:16]

def _build_tags(hashtag, tickers, content_type):
    tags = ["instagram"]
    if hashtag: tags.append(f"#{hashtag}")
    if content_type and content_type not in ("unknown","general"): tags.append(content_type)
    crypto_tags = {"crypto","bitcoin","ethereum","defi","btc","eth"}
    if (hashtag and hashtag.lower() in crypto_tags) or any(".X" in t for t in tickers[:3]): tags.append("crypto")
    tags.extend(f"${t}" for t in tickers[:3]); return tags

def build_signal(post, platform="instagram", hashtag=""):
    caption = post.get("caption",""); tickers = extract_tickers(caption)
    direction, confidence = score_sentiment(caption); content_type = classify_content(caption)
    likes = post.get("likes",0); comments = post.get("comments",0); eng = likes + comments
    if eng >= 1000: confidence = min(confidence + 0.1, 0.95)
    elif eng >= 100: confidence = min(confidence + 0.05, 0.95)
    return {"id": make_signal_id(platform, post.get("id", str(uuid.uuid4()))),
        "type": "sentiment", "source_url": post.get("url",""), "source_author": post.get("author",""),
        "title": "", "body": caption[:500], "ticker_or_market": tickers[0] if tickers else hashtag,
        "direction": direction, "confidence": confidence, "urgency": detect_urgency(caption),
        "engagement": {"upvotes": likes, "comments": comments, "shares": 0},
        "tags": _build_tags(hashtag, tickers, content_type),
        "raw_data": {"all_tickers": tickers, "content_type": content_type, "hashtag": hashtag,
            "author_followers": post.get("author_followers",0), "media_type": post.get("media_type","image"),
            "timestamp": post.get("timestamp","")},
        "extracted_at": datetime.now(timezone.utc).isoformat()}

def aggregate_hashtag_sentiment(signals):
    agg = {}
    for s in signals:
        t = s.get("ticker_or_market","")
        if not t: continue
        if t not in agg:
            agg[t] = {"bullish":0,"bearish":0,"neutral":0,"unknown":0,"total":0,"conf_sum":0.0,"likes_sum":0,"comments_sum":0}
        d = s.get("direction","unknown"); agg[t][d] = agg[t].get(d,0) + 1
        agg[t]["total"] += 1; agg[t]["conf_sum"] += s.get("confidence",0)
        agg[t]["likes_sum"] += s.get("engagement",{}).get("upvotes",0)
        agg[t]["comments_sum"] += s.get("engagement",{}).get("comments",0)
    return {t: {"bullish":d["bullish"],"bearish":d["bearish"],"neutral":d["neutral"],"total":d["total"],
        "avg_confidence": round(d["conf_sum"]/d["total"],2) if d["total"] else 0,
        "total_likes":d["likes_sum"],"total_comments":d["comments_sum"],
        "bull_bear_ratio": round(d["bullish"]/max(d["bearish"],1),2)} for t,d in agg.items()}

def compute_velocity(signals, window_minutes=60):
    counts = {}
    for s in signals:
        t = s.get("ticker_or_market","")
        if t: counts[t] = counts.get(t,0) + 1
    return counts
