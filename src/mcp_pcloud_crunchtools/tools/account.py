"""Account operations against the pCloud API."""

from __future__ import annotations

from ..client import get_client
from .formatting import BYTES_PER_GB

PERCENT = 100


async def get_user_info() -> str:
    """Return the authenticated account's profile and quota usage."""
    payload = await get_client().call("userinfo", context="account")

    quota = int(payload.get("quota", 0))
    used = int(payload.get("usedquota", 0))
    used_gb = used / BYTES_PER_GB
    total_gb = quota / BYTES_PER_GB
    used_pct = (used / quota * PERCENT) if quota else 0.0

    return (
        "pCloud User Info:\n\n"
        f"Email: {payload.get('email', '')}\n"
        f"Verified: {'Yes' if payload.get('emailverified') else 'No'}\n"
        f"Registered: {payload.get('registered', '')}\n\n"
        "Storage:\n"
        f"  Used: {used_gb:.2f} GB ({used_pct:.1f}%)\n"
        f"  Total: {total_gb:.2f} GB"
    )
