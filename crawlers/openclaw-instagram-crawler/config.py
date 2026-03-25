"""Instagram crawler configuration."""
import os
from dotenv import load_dotenv
load_dotenv()

PLATFORM = "instagram"
USER_AGENT = os.getenv("INSTAGRAM_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

HASHTAGS = ["crypto","trading","investing","bitcoin","stocks","fintok","ethereum","defi","forex","stockmarket"]
INFLUENCERS = ["raikirillin","investwithhenry","markettradertv","financialeducation","meetkevin","caaborern"]

HASHTAG_INTERVAL_SEC = int(os.getenv("HASHTAG_INTERVAL_SEC", "3600"))
PROFILE_INTERVAL_SEC = int(os.getenv("PROFILE_INTERVAL_SEC", "86400"))
POSTS_PER_HASHTAG = int(os.getenv("POSTS_PER_HASHTAG", "30"))
MAX_CAPTION_CHARS = 500

REQUEST_DELAY_MIN = float(os.getenv("REQUEST_DELAY_MIN", "3.0"))
REQUEST_DELAY_MAX = float(os.getenv("REQUEST_DELAY_MAX", "5.0"))
BACKOFF_BASE_SEC = 5.0
BACKOFF_MAX_SEC = 300.0
MAX_RETRIES = 3

BASE_URL = "https://www.instagram.com"
HASHTAG_URL = BASE_URL + "/explore/tags/{hashtag}/"
PROFILE_URL = BASE_URL + "/{username}/"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
