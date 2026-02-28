from playwright.sync_api import sync_playwright
import markdownify

def fetch_dynamic(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # 자바스크립트 실행 후 전체 HTML 획득
            html_content = page.content()
            browser.close()
            
            # AI가 읽기 좋게 마크다운으로 변환
            return markdownify.markdownify(html_content, heading_style="ATX")
    except Exception as e:
        print(f"Playwright 에러: {e}")
        return None