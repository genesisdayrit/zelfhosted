from .weather import get_weather
from .polymarket import get_polymarket_opportunities
from .arxiv import get_arxiv_articles
from .photos import get_latest_photos
from .twitter import post_tweet
from .linear import get_linear_issues

# Register all tools - add new tools here
tools = [get_weather, get_polymarket_opportunities, get_arxiv_articles, get_latest_photos, post_tweet, get_linear_issues]
tools_by_name = {t.name: t for t in tools}

__all__ = ["tools", "tools_by_name"]

