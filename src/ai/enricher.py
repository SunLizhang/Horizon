"""Lightweight content enrichment — second pass for high-scoring items.

Simplified to only add value for Feishu daily briefings:
- Generate Chinese key details + background from article content (no web search)
- No English fields, no references/sources list
- ~60% fewer tokens than the original bilingual enrichment
"""

import asyncio
import json
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn

from .client import AIClient
from .utils import parse_json_response
from ..models import ContentItem


LIGHT_ENRICHMENT_SYSTEM = """你是一个新闻摘要助手，为一篇科技/财经新闻写出简洁的中文分析。

输出要求：
1. **关键细节**（key_details_zh，2-3句话）：补充原文中的技术名称、金额、时间线等具体信息
2. **背景知识**（background_zh，1-2句话）：如果涉及不常见的概念，用一句话解释；如果新闻自解释，填空字符串

规则：
- 只用原文内容，不要编造信息
- 不要写英文
- 如果新闻已经一目了然，background_zh 填空字符串
- 只输出 JSON"""

LIGHT_ENRICHMENT_USER = """为以下新闻写出中文关键细节和背景知识：

标题：{title}
摘要：{summary}
标签：{tags}
原文内容：{content}

输出 JSON：
{{
  "key_details_zh": "<2-3句中文关键细节>",
  "background_zh": "<1-2句背景知识，或空字符串>"
}}"""


class ContentEnricher:
    """Enriches high-scoring content items with lightweight Chinese background."""

    def __init__(self, ai_client: AIClient):
        self.client = ai_client

    def _get_concurrency(self) -> int:
        config = getattr(self.client, "config", None)
        concurrency = getattr(config, "enrichment_concurrency", 1)
        return max(concurrency, 1)

    async def enrich_batch(self, items: List[ContentItem]) -> None:
        """Enrich items in-place with Chinese key details and background."""
        concurrency = self._get_concurrency()
        semaphore = asyncio.Semaphore(concurrency)

        async def _process(item: ContentItem, progress_task) -> None:
            async with semaphore:
                try:
                    await self._enrich_item(item)
                except Exception as e:
                    print(f"Error enriching item {item.id}: {e}")
            progress.advance(progress_task)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("Enriching", total=len(items))
            coros = [_process(item, task) for item in items]
            await asyncio.gather(*coros)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    async def _enrich_item(self, item: ContentItem) -> None:
        """Lightweight enrichment: generate Chinese key_details + background."""
        content_text = ""
        if item.content:
            if "--- Top Comments ---" in item.content:
                content_text = item.content.split("--- Top Comments ---", 1)[0].strip()[:2000]
            else:
                content_text = item.content[:2000]

        tags = ", ".join(item.ai_tags) if item.ai_tags else ""

        user_prompt = LIGHT_ENRICHMENT_USER.format(
            title=item.title,
            summary=item.ai_summary or item.title,
            tags=tags,
            content=content_text,
        )

        response = await self.client.complete(
            system=LIGHT_ENRICHMENT_SYSTEM,
            user=user_prompt,
        )

        result = parse_json_response(response)
        if result is None:
            return

        if result.get("key_details_zh"):
            item.metadata["detailed_summary_zh"] = result["key_details_zh"]
        if result.get("background_zh"):
            item.metadata["background_zh"] = result["background_zh"]
