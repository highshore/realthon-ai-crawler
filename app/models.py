# app/models.py
from pydantic import BaseModel
from typing import List, Optional

class NoticeItem(BaseModel):
    title: str
    summary: str
    originalUrl: str
    sourceName: str
    category: Optional[str] = "공지사항"
    relevanceScore: Optional[float] = 0.0
    timestamp: str

class CallbackData(BaseModel):
    userId: str
    data: List[NoticeItem]