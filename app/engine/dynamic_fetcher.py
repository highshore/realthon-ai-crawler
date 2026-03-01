import asyncio
from playwright.async_api import async_playwright

async def fetch_dynamic(url):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            content = await page.content()
            await browser.close()
            return content
    except Exception as e:
        print(f"Playwright 에러: {e}")
        return None