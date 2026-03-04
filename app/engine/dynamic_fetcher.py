import asyncio

import sys
from playwright.async_api import async_playwright
from urllib.parse import urlparse
from app.utils.helpers import guess_site_name
import logging

LOG = logging.getLogger(__name__)
async def fetch_dynamic(url):
    async with async_playwright() as p:
        # 1. 브라우저 실행 (새로운 인스턴스)
        browser = await p.chromium.launch(headless=True)
        
        # 2. 🚨 [중요] 새로운 컨텍스트 생성 (쿠키, 캐시 완전 분리)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            LOG.info(f"🌐 [Dynamic] 이동 중: {url}")
            # 3. 이동 시 timeout과 wait_until을 확실히 줌
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 4. 서강대인지 토스인지 확인 사살 (로그 찍기)
            current_url = page.url
            LOG.info(f"📍 [Dynamic] 현재 실제 접속 주소: {current_url}")
            
            await page.wait_for_timeout(2000) # 안정화 시간
            content = await page.content()
            
        except Exception as e:
            LOG.error(f"❌ [Dynamic] 에러 발생: {e}")
            content = None
        finally:
            # 5. 🚨 [필수] 다 썼으면 문 닫기!
            await context.close()
            await browser.close()
            
        return content