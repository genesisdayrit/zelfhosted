"""
Polymarket Trade Opportunities Tool

Identifies high-confidence trading opportunities on Polymarket.
Based on: https://docs.polymarket.com/developers/gamma-markets-api/get-markets
"""

import json
import requests
from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool

GAMMA_API = "https://gamma-api.polymarket.com"

# Filters
MIN_HOURS_REMAINING = 0.5
MAX_HOURS_REMAINING = 48.0
MIN_PROBABILITY_EXTREME = 0.85


def get_markets_ending_soon(hours: int = 48) -> list:
    """Fetch active markets ending within specified hours."""
    now = datetime.now(timezone.utc)
    end_max = now + timedelta(hours=hours)
    
    params = {
        "active": "true",
        "closed": "false",
        "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_date_max": end_max.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "order": "endDate",
        "ascending": "true",
        "limit": 500,
    }
    
    response = requests.get(f"{GAMMA_API}/markets", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_market_data(market: dict) -> dict:
    """Extract and compute all relevant trading data from a market."""
    yes_price = None
    no_price = None
    
    try:
        prices_str = market.get('outcomePrices', '[]')
        if isinstance(prices_str, str):
            prices = json.loads(prices_str)
        else:
            prices = prices_str
        
        if prices and len(prices) >= 2:
            yes_price = float(prices[0])
            no_price = float(prices[1])
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    
    # Calculate hours remaining
    hours_remaining = 0
    end_date_str = market.get('endDateIso') or market.get('endDate')
    if end_date_str:
        try:
            if 'T' not in end_date_str and len(end_date_str) == 10:
                end_date = datetime.fromisoformat(end_date_str + "T23:59:59+00:00")
            else:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            hours_remaining = max(0, (end_date - now).total_seconds() / 3600)
        except (ValueError, TypeError):
            pass
    
    # Determine recommended side and calculate returns
    recommended_side = None
    buy_price = None
    win_probability = None
    
    if yes_price is not None and no_price is not None:
        if yes_price >= 0.5:
            recommended_side = "YES"
            buy_price = yes_price
            win_probability = yes_price
        else:
            recommended_side = "NO"
            buy_price = no_price
            win_probability = no_price
    
    # Calculate potential returns
    profit_pct = None
    profit_100 = None
    
    if buy_price and buy_price > 0:
        profit_pct = ((1 - buy_price) / buy_price) * 100
        profit_100 = (1 - buy_price) / buy_price * 100
    
    # Calculate extremity (distance from 50%)
    extremity = abs(yes_price - 0.5) if yes_price is not None else 0
    
    return {
        'question': market.get('question', ''),
        'yes_price': yes_price,
        'no_price': no_price,
        'hours_remaining': hours_remaining,
        'recommended_side': recommended_side,
        'buy_price': buy_price,
        'win_probability': win_probability,
        'profit_pct': profit_pct,
        'profit_100': profit_100,
        'extremity': extremity,
        'slug': market.get('slug', ''),
        'volume_24hr': market.get('volume24hr', ''),
        'liquidity': market.get('liquidity', ''),
    }


def filter_opportunities(markets: list) -> list:
    """Filter for actionable trading opportunities."""
    filtered = []
    
    for market in markets:
        if market['buy_price'] is None:
            continue
        if market['hours_remaining'] < MIN_HOURS_REMAINING:
            continue
        if market['extremity'] < (MIN_PROBABILITY_EXTREME - 0.5):
            continue
        if market['buy_price'] >= 0.995 or market['buy_price'] <= 0.005:
            continue
        
        filtered.append(market)
    
    return filtered


@tool
def get_polymarket_opportunities(max_results: int = 10) -> str:
    """Find high-confidence trading opportunities on Polymarket.
    
    Returns markets ending within 48 hours that have extreme probabilities (≥85% or ≤15%),
    sorted by profit potential.
    
    Args:
        max_results: Maximum number of opportunities to return (default 10)
    """
    try:
        # Fetch markets
        raw_markets = get_markets_ending_soon(hours=int(MAX_HOURS_REMAINING))
        
        # Parse and filter
        markets = [parse_market_data(m) for m in raw_markets]
        opportunities = filter_opportunities(markets)
        
        if not opportunities:
            return "No high-confidence trading opportunities found at this time. Try again later or adjust the filters."
        
        # Sort by profit potential
        opportunities.sort(key=lambda x: x['profit_pct'] or 0, reverse=True)
        opportunities = opportunities[:max_results]
        
        # Format response
        lines = [f"Found {len(opportunities)} high-confidence opportunities:\n"]
        
        for i, m in enumerate(opportunities, 1):
            side = m['recommended_side']
            price = f"${m['buy_price']:.2f}"
            prob = f"{m['win_probability']*100:.0f}%"
            profit = f"{m['profit_pct']:.1f}%"
            profit_100 = f"${m['profit_100']:.2f}"
            hours = f"{m['hours_remaining']:.1f}h"
            url = f"https://polymarket.com/event/{m['slug']}" if m['slug'] else ""
            
            lines.append(
                f"{i}. {m['question']}\n"
                f"   → Buy {side} at {price} (probability: {prob})\n"
                f"   → Potential profit: {profit} ({profit_100} on $100 bet)\n"
                f"   → Ends in: {hours}\n"
                f"   → {url}\n"
            )
        
        lines.append("\n💡 Note: 'Profit' assumes the market resolves in your favor. Higher profit % = lower win probability.")
        
        return "\n".join(lines)
        
    except requests.RequestException as e:
        return f"Error fetching Polymarket data: {str(e)}"

