import asyncio

import sys
from playwright.async_api import async_playwright


async def fetch_dynamic(url):
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000) # 3초만 딱 더 기다리기
            content = await page.content()
            await browser.close()
            return content
    except Exception as e:
        print(f"Playwright 에러: {e}")
        return None