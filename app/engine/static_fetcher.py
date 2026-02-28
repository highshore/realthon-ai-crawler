import requests
import logging

LOG = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
})

def fetch_static(url):
    try:
        resp = session.get(url, timeout=15)
        resp.encoding = 'utf-8'
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        LOG.error(f"정적 수집 중 에러: {e}")
        return None