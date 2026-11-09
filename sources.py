"""Small official-source example registry, not an editorial priority list."""
from __future__ import annotations

OFFICIAL: list[dict[str, object]] = [
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/",
     "type": "web", "tier": 1, "refresh_hours": 24},
    {"name": "Anthropic Research", "url": "https://www.anthropic.com/research",
     "type": "web", "tier": 1, "refresh_hours": 24},
    {"name": "AWS Machine Learning Blog", "url": "https://aws.amazon.com/blogs/machine-learning/feed/",
     "type": "rss", "tier": 1, "refresh_hours": 24},
]
RSS_FEEDS = OFFICIAL
DEFAULT_ITEMS_PER_FEED = 5
SOURCE_GROUPS = {"official": OFFICIAL, "cloudrun": OFFICIAL, "all": OFFICIAL}


def get_feeds(group: str = "official") -> list[dict[str, object]]:
    normalized = (group or "official").strip().lower()
    if normalized not in SOURCE_GROUPS:
        raise ValueError(f"Unknown source group: {group}")
    return [dict(item) for item in SOURCE_GROUPS[normalized]]
