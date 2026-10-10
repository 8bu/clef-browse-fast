import os

import httpx

from .config import neo_urls


def neo_status() -> dict[str, bool]:
    """Report whether Neo answers on its MCP port and on its CDP port."""
    mcp_url, cdp_url = neo_urls()
    mcp_ok = cdp_ok = False
    try:
        from .neo import NeoMcp

        client = NeoMcp(mcp_url)
        client.call_tool("run", {"code": "return (await browser.pages.list()).length"})
        client.close()
        mcp_ok = True
    except Exception:
        pass
    try:
        response = httpx.get(f"{cdp_url.rstrip('/')}/json/version", timeout=3)
        cdp_ok = response.is_success and str(response.json().get("Browser", "")).startswith("Chrome/")
    except Exception:
        pass
    return {"neo_mcp": mcp_ok, "neo_cdp": cdp_ok}


def clef_env_ready() -> bool:
    return bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_AUTH_TOKEN"))


def check_all() -> dict[str, bool]:
    return {**neo_status(), "clef_env": clef_env_ready()}
