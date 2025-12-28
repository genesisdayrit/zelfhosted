from .weather import get_weather
from .polymarket import get_polymarket_opportunities
from .arxiv import get_arxiv_articles
from .photos import get_latest_photos
from .twitter import post_tweet
from .linear import get_linear_issues
from .mercury import get_mercury_balance
from .subway import get_subway_arrivals, get_train_arrivals_at_station, get_nearby_subway_stations, get_nearby_subway_arrivals
from .youtube import search_youtube_song
from .exa import exa_search, exa_find_similar, exa_answer

# Register all tools - add new tools here
tools = [get_weather, get_polymarket_opportunities, get_arxiv_articles, get_latest_photos, post_tweet, get_linear_issues, get_mercury_balance, get_subway_arrivals, get_train_arrivals_at_station, get_nearby_subway_stations, get_nearby_subway_arrivals, search_youtube_song, exa_search, exa_find_similar, exa_answer]
tools_by_name = {t.name: t for t in tools}

__all__ = ["tools", "tools_by_name"]

