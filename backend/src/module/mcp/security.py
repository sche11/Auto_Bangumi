"""MCP access control: configurable IP whitelist and bearer token authentication."""

import ipaddress
import logging
from functools import lru_cache

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from module.conf import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=128)
def _parse_network(cidr: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    try:
        return ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        logger.warning("[MCP] Invalid CIDR in whitelist: %s", cidr)
        return None


def _is_allowed(host: str, whitelist: list[str]) -> bool:
    """Return True if *host* falls within any CIDR range in *whitelist*."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    for cidr in whitelist:
        net = _parse_network(cidr)
        if net and addr in net:
            return True
    return False


def clear_network_cache():
    """Clear the parsed network cache (call after config reload)."""
    _parse_network.cache_clear()


class McpAccessMiddleware(BaseHTTPMiddleware):
    """Configurable access control for MCP endpoint.

    Checks client IP against ``settings.security.mcp_whitelist`` CIDR ranges,
    and ``Authorization`` header against ``settings.security.mcp_tokens``.
    If the whitelist is empty and no tokens are configured, all access is denied.
    """

    async def dispatch(self, request: Request, call_next):
        # Check bearer token first
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token and token in settings.security.mcp_tokens:
                return await call_next(request)

        # Check IP whitelist
        client_host = request.client.host if request.client else None
        if client_host and _is_allowed(client_host, settings.security.mcp_whitelist):
            return await call_next(request)

        logger.warning("[MCP] Rejected connection from %s", client_host)
        return JSONResponse(
            status_code=403,
            content={"error": "MCP access denied"},
        )
