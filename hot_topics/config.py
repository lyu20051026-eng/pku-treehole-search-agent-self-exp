"""Defaults are independent of private credentials and old search settings."""
from dataclasses import dataclass, fields
import math


@dataclass(frozen=True)
class HotConfig:
    hours: int = 24
    top_posts: int = 30
    page_size: int = 30
    max_scan_posts: int = 5000
    max_scan_pages: int = 200
    max_comment_pages: int = 200
    request_delay: float = 1.0
    max_retries: int = 3
    min_keyword_posts: int = 3
    min_favorites: int = 5
    min_likes: int = 3
    min_comments: int = 10
    high_percentile: float = 0.9
    topic_similarity: float = 0.25
    output_dir: str = 'data/hot_topics'
    context_chars: int = 18000
    max_summary_chunks: int = 40
    only_export: bool = False

    def __post_init__(self):
        if self.hours not in (24, 72, 168):
            raise ValueError('时间范围必须为 24、72 或 168 小时')
        for name in ('top_posts', 'page_size', 'max_scan_posts', 'max_scan_pages',
                     'max_comment_pages', 'max_retries', 'min_keyword_posts',
                     'context_chars', 'max_summary_chunks'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(name + ' must be a positive integer')
        if self.context_chars < 2000:
            raise ValueError('context_chars must be at least 2000')
        for name in ('min_favorites', 'min_likes', 'min_comments', 'request_delay'):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(name + ' must be finite and nonnegative')
        for name in ('high_percentile', 'topic_similarity'):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(name + ' must be between 0 and 1')

    @classmethod
    def from_module(cls, module, **overrides):
        settings = {f.name: getattr(module, 'HOT_' + f.name.upper())
                    for f in fields(cls) if hasattr(module, 'HOT_' + f.name.upper())}
        settings.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**settings)
