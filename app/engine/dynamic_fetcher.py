import asyncio
import logging
from playwright.async_api import async_playwright
from app.utils.helpers import guess_site_name

LOG = logging.getLogger(__name__)

async def fetch_dynamic(url):
    async with async_playwright() as p:
        # 브라우저 실행 (가끔 토스가 봇 감지를 하니까 위장을 좀 더 함)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1024}
        )
        page = await context.new_page()
        
        content = None
        try:
            LOG.info(f"🌐 [Dynamic] {url} 접속 시도...")
            
            # 1. 🚨 [중요] 페이지 이동 및 네트워크 안정화 대기
            # wait_until="networkidle"은 모든 API 요청이 끝날 때까지 기다려줘
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 2. 🚨 [토스 필살기] 본문(article)이 뜰 때까지 대기
            # 토스 상세 페이지는 'article' 태그 안에 모든 내용이 들어있어
            try:
                LOG.info("⏳ 본문(article) 요소 로딩 대기 중...")
                await page.wait_for_selector("article", timeout=10000) 
                
                # 본문이 떴어도 텍스트가 채워지는 찰나의 시간이 필요함
                await page.wait_for_timeout(2000) 
            except:
                LOG.warning("⚠️ article 태그를 못 찾았습니다. 다른 요소를 탐색합니다.")

            # 3. 🚨 [서강대/일반 목록 필살기] 공지 목록 링크가 뜰 때까지 대기
            try:
                # 목록 페이지라면 최소한 공지사항 링크(a) 하나는 있어야 함
                await page.wait_for_selector("main a, .notice_list a", timeout=5000)
            except:
                pass

            # 4. 최종 확인: 페이지 바닥까지 슬쩍 스크롤 (게으른 로딩 방지)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            await page.wait_for_timeout(1000)
            
            content = await page.content()
            LOG.info(f"📍 [Dynamic] 수집 완료 (HTML 길이: {len(content)})")
            
        except Exception as e:
            LOG.error(f"❌ [Dynamic] 에러 발생: {e}")
            # 에러 나도 현재까지 긁힌 게 있으면 가져오기
            try:
                content = await page.content()
            except:
                content = None
        finally:
            await browser.close()
            
        return content