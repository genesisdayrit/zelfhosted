"""
Mercury Account Balance Tool

Fetches account balance from Mercury banking API.
Requires environment variables:
  - MERCURY_TOKEN
  - MERCURY_CHECKING_ACCOUNT_UUID (for checking)
  - MERCURY_SAVINGS_ACCOUNT_UUID (for savings)
"""

import os
import httpx
from langchain_core.tools import tool

MERCURY_API_URL = "https://api.mercury.com/api/v1"

http_client = httpx.Client(timeout=30.0)


def _fetch_account_balance(account_id: str, api_token: str, account_type: str) -> dict:
    """Fetch balance for a single account. Returns dict with account info or error."""
    response = http_client.get(
        f"{MERCURY_API_URL}/account/{account_id}",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
    )
    
    if response.status_code != 200:
        return {"error": f"Error from Mercury API: {response.status_code} - {response.text}"}
    
    account = response.json()
    return {
        "type": account_type,
        "name": account.get("name", "Unknown Account"),
        "current_balance": account.get("currentBalance", 0),
        "available_balance": account.get("availableBalance", 0),
        "currency": account.get("currency", "USD"),
        "status": account.get("status", "unknown"),
    }


def _format_account(account: dict) -> list[str]:
    """Format a single account's info as lines."""
    type_label = account["type"].capitalize()
    pending = account["current_balance"] - account["available_balance"]
    
    lines = [
        f"💰 Mercury {type_label} Account: {account['name']}",
        f"   Current Balance: ${account['current_balance']:,.2f} {account['currency']}",
        f"   Available Balance: ${account['available_balance']:,.2f} {account['currency']}",
    ]
    
    if pending != 0:
        lines.append(f"   Pending: ${pending:,.2f} {account['currency']}")
    
    lines.append(f"   Status: {account['status']}")
    
    return lines


@tool
def get_mercury_balance(account_type: str = "both") -> str:
    """Get the current balance of Mercury bank accounts.
    
    Args:
        account_type: Which account to check - "checking", "savings", or "both" (default: "both")
    
    Returns the current balance, available balance, and account status.
    """
    api_token = os.environ.get("MERCURY_TOKEN")
    if not api_token:
        return "Error: Missing MERCURY_TOKEN environment variable"
    
    account_type = account_type.lower()
    if account_type not in ("checking", "savings", "both"):
        return "Error: account_type must be 'checking', 'savings', or 'both'"
    
    # Determine which accounts to fetch
    accounts_to_fetch = []
    if account_type in ("checking", "both"):
        checking_id = os.environ.get("MERCURY_CHECKING_ACCOUNT_UUID")
        if checking_id:
            accounts_to_fetch.append(("checking", checking_id))
        elif account_type == "checking":
            return "Error: Missing MERCURY_CHECKING_ACCOUNT_UUID environment variable"
    
    if account_type in ("savings", "both"):
        savings_id = os.environ.get("MERCURY_SAVINGS_ACCOUNT_UUID")
        if savings_id:
            accounts_to_fetch.append(("savings", savings_id))
        elif account_type == "savings":
            return "Error: Missing MERCURY_SAVINGS_ACCOUNT_UUID environment variable"
    
    if not accounts_to_fetch:
        return "Error: No account UUIDs configured in environment variables"
    
    try:
        results = []
        total_current = 0
        total_available = 0
        currency = "USD"
        
        for acct_type, acct_id in accounts_to_fetch:
            account = _fetch_account_balance(acct_id, api_token, acct_type)
            
            if "error" in account:
                results.append(f"❌ {acct_type.capitalize()}: {account['error']}")
            else:
                results.extend(_format_account(account))
                total_current += account["current_balance"]
                total_available += account["available_balance"]
                currency = account["currency"]
                results.append("")  # blank line between accounts
        
        # Add total if showing both accounts
        if len(accounts_to_fetch) > 1 and total_current > 0:
            results.append("━" * 40)
            results.append(f"📊 Total Current Balance: ${total_current:,.2f} {currency}")
            results.append(f"   Total Available: ${total_available:,.2f} {currency}")
        
        return "\n".join(results).strip()
        
    except Exception as e:
        return f"Error fetching Mercury balance: {str(e)}"
