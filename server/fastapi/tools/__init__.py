from .weather import get_weather
from .polymarket import get_polymarket_opportunities

# Register all tools - add new tools here
tools = [get_weather, get_polymarket_opportunities]
tools_by_name = {t.name: t for t in tools}

__all__ = ["tools", "tools_by_name"]

