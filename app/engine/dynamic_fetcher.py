import asyncio

import sys
from playwright.async_api import async_playwright
from urllib.parse import urlparse
from app.utils.helpers import guess_site_name
import logging

LOG = logging.getLogger(__name__)
async def fetch_dynamic(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # 1. 일단 이동
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 2. 🚨 [핵심] 서강대 공지 목록의 특정 요소가 나타날 때까지 대기
            # 서강대는 보통 공지사항 리스트에 'Academic'이나 'Notice' 관련 클래스가 있어.
            # 만약 클래스명을 모르면, 최소한 <a> 태그가 생길 때까지 기다려보자.
            try:
                await page.wait_for_selector("main a", timeout=10000) 
            except:
                LOG.warning("⚠️ 특정 셀렉터를 못 찾았지만 일단 계속 진행합니다.")
            
            # 3. 자바스크립트가 완전히 돌 시간을 강제로 3초 더 줌
            await page.wait_for_timeout(3000) 
            
            content = await page.content()
            LOG.info(f"📍 [Dynamic] 수집 완료 (HTML 길이: {len(content)})")
            
        except Exception as e:
            LOG.error(f"❌ [Dynamic] 에러: {e}")
            content = None
        finally:
            await browser.close()
            
        return content