from urllib.parse import urlparse


def guess_site_name(url: str) -> str:
    """URL 도메인을 분석해 사이트 이름을 추측합니다."""
    domain = urlparse(url).netloc
    mapping = {
        "sogang.ac.kr": "서강대학교 공지",
        "korea.ac.kr": "고려대학교 공지",
        "toss.im": "토스 채용 블로그",
    }
    for key, name in mapping.items():
        if key in domain: return name
    return domain.replace("www.", "").split('.')[0].capitalize()

