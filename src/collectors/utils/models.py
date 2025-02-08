from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

@dataclass
class NewsArticle:
    title: str
    content: str
    url: str
    press: str
    category: str
    published_at: datetime
    collected_at: datetime = datetime.now()
    keywords: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "press": self.press,
            "category": self.category,
            "published_at": self.published_at.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "keywords": self.keywords
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NewsArticle':
        return cls(
            title=data["title"],
            content=data["content"],
            url=data["url"],
            press=data["press"],
            category=data["category"],
            published_at=datetime.fromisoformat(data["published_at"]),
            collected_at=datetime.fromisoformat(data["collected_at"]),
            keywords=data.get("keywords")
        ) 