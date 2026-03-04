import requests
import logging

LOG = logging.getLogger(__name__)

def fetch_static(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # 1. 목록이나 본문을 빠르게 긁어옴
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 2. 한글 깨짐 방지 (고려대 등 국내 사이트 필수)
        response.encoding = response.apparent_encoding
        return response.text
    except Exception as e:
        LOG.error(f"❌ 정적 수집 실패 ({url}): {e}")
        return ""