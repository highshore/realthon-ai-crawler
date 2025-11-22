from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
LOG = logging.getLogger("korea_uni")

BASE_URL = "https://info.korea.ac.kr/info/board/"
TIMEZONE = ZoneInfo("Asia/Seoul")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
LOOKBACK_DAYS = 7

SENDER_KEY = "1763d8030dde5f5f369ea0a088598c2fb4c792ab"
SECRET_KEY = "PuyyHGNZ"
APP_KEY = "LROcHEW7abBbFhzc"
TEMPLATE_CODE = "send-article"

RECIPIENTS = [
    {"name": "고려대 학부생 김수겸", "contact": "01068584123"},
    {"name": "고려대 학부생 고연오", "contact": "01026570090"},
]

BOARDS = [
    {"name": "학부공지", "category": "notice_under"},
    {"name": "학부장학", "category": "scholarship_under"},
    {"name": "정보대소식", "category": "news"},
    {"name": "취업정보", "category": "course_job"},
    {"name": "프로그램", "category": "course_program"},
    {"name": "인턴십", "category": "course_intern"},
    {"name": "공모전", "category": "course_competition"},
]

session = requests.Session()


def send_kakao(contact: str, template_code: str, template_param: dict) -> dict[str, Any]:
    payload = {
        "senderKey": SENDER_KEY,
        "templateCode": template_code,
        "recipientList": [{"recipientNo": contact, "templateParameter": template_param}],
    }
    headers = {
        "X-Secret-Key": SECRET_KEY,
        "Content-Type": "application/json;charset=UTF-8",
    }
    url = f"https://api-alimtalk.cloud.toast.com/alimtalk/v2.2/appkeys/{APP_KEY}/messages"
    resp = session.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        LOG.error("Kakao send failed (%s) %s", resp.status_code, resp.text)
        resp.raise_for_status()
    LOG.info("Kakao send ok for %s", contact)
    if resp.headers.get("Content-Type", "").startswith("application/json"):
        return resp.json()
    return {"status": resp.status_code}


def fetch_board(board: dict[str, str]) -> tuple[str, str]:
    page_url = f"{BASE_URL}{board['category']}.do"
    resp = session.get(page_url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return page_url, resp.text


def parse_posts(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    today = datetime.now(TIMEZONE).date()
    cutoff = today - timedelta(days=LOOKBACK_DAYS - 1)
    posts: list[dict[str, str]] = []
    for row in soup.select("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        date_text = cells[-1].get_text(strip=True)
        try:
            row_date = datetime.strptime(date_text, "%Y.%m.%d").date()
        except ValueError:
            continue
        if row_date < cutoff:
            continue
        link_tag = row.select_one("a.article-title")
        if not link_tag:
            continue
        href = (link_tag.get("href") or "").replace("amp;", "")
        title = link_tag.get_text(strip=True)
        posts.append({"title": title, "link": urljoin(base_url, href)})
    return posts


def notify(board: dict[str, str], posts: list[dict[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for post in posts:
        title = f"고려대 정보대 공지 ({board['name']})\n\n{post['title']}"
        for target in RECIPIENTS:
            params = {
                "korean-title": title,
                "customer-name": target["name"],
                "article-link": post["link"],
            }
            try:
                data = send_kakao(target["contact"], TEMPLATE_CODE, params)
                results.append(
                    {
                        "board": board["name"],
                        "title": post["title"],
                        "recipient": target["contact"],
                        "status": data,
                    }
                )
            except Exception as exc:
                LOG.exception("Kakao send error: %s", exc)
                results.append(
                    {
                        "board": board["name"],
                        "title": post["title"],
                        "recipient": target["contact"],
                        "error": str(exc),
                    }
                )
    return results


def process_board(board: dict[str, str]) -> dict[str, Any]:
    try:
        page_url, html = fetch_board(board)
        posts = parse_posts(html, page_url)
    except Exception as exc:
        LOG.exception("Board fetch error for %s: %s", board["name"], exc)
        return {"board": board["name"], "error": str(exc), "posts": [], "sent": []}
    sent = notify(board, posts)
    return {"board": board["name"], "posts": posts, "sent": sent}


def crawl() -> dict[str, Any]:
    report = []
    for board in BOARDS:
        report.append(process_board(board))
    total_posts = sum(len(entry["posts"]) for entry in report)
    return {"totalPosts": total_posts, "boards": report}


def lambda_handler(event: dict[str, Any] | None = None, context: Any | None = None) -> dict[str, Any]:
    LOG.info("Lambda trigger: %s", json.dumps(event or {}))
    return crawl()


if __name__ == "__main__":
    print(json.dumps(crawl(), ensure_ascii=False, indent=2))