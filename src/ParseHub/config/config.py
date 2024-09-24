import sys
from os import getenv
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


class ParseHubConfig:
    def __init__(self):
        self.cache_time = int(getenv("CACHE_TIME", 86400))
        self.ai_summary = getenv("AI_SUMMARY", "True") == "True"

        self.xhs_api = getenv("XHS_API")
        self.xhs_cookie = getenv("XHS_COOKIE")
        self.douyin_api = getenv("DOUYIN_API")

        parent_dir = Path(sys.argv[0]).parent
        self.DOWNLOAD_DIR = getenv("DOWNLOAD_DIR", parent_dir / Path("downloads/"))

        self.provider = getenv("PROVIDER", "openai").lower()
        self.api_key = getenv("API_KEY")
        self.base_url = getenv("BASE_URL")
        self.model = getenv("MODEL", "gpt-4o-mini")
        self.whisper_api = getenv("WHISPER_API")


ph_cfg = ParseHubConfig()
