from .weather import get_weather

# Register all tools - add new tools here
tools = [get_weather]
tools_by_name = {t.name: t for t in tools}

__all__ = ["tools", "tools_by_name"]

