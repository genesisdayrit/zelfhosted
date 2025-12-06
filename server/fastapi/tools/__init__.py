from .weather import get_weather
from .polymarket import get_polymarket_opportunities
from .arxiv import get_arxiv_articles
from .photos import get_latest_photos

# Register all tools - add new tools here
tools = [get_weather, get_polymarket_opportunities, get_arxiv_articles, get_latest_photos]
tools_by_name = {t.name: t for t in tools}

__all__ = ["tools", "tools_by_name"]

