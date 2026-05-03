import re
import urllib.parse
import requests

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
_STEAM_ID_RE = re.compile(r"https://steamcommunity\.com/openid/id/(\d+)$")


def get_auth_url(return_to: str, realm: str) -> str:
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID_URL}?{urllib.parse.urlencode(params)}"


def verify_callback(params: dict) -> str | None:
    """Verify the OpenID assertion with Steam and return SteamID64, or None on failure."""
    verify_params = {k: v for k, v in params.items()}
    verify_params["openid.mode"] = "check_authentication"

    resp = requests.post(STEAM_OPENID_URL, data=verify_params, timeout=10)
    if not resp.ok or "is_valid:true" not in resp.text:
        return None

    claimed_id = params.get("openid.claimed_id", "")
    match = _STEAM_ID_RE.match(claimed_id)
    return match.group(1) if match else None


def fetch_profile(steam_id: str, api_key: str) -> dict:
    """Return display name and avatar URL for the given SteamID64."""
    resp = requests.get(
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
        params={"key": api_key, "steamids": steam_id},
        timeout=10,
    )
    players = resp.json().get("response", {}).get("players", [])
    if not players:
        return {"name": "Unknown", "avatar": ""}
    p = players[0]
    return {"name": p.get("personaname", "Unknown"), "avatar": p.get("avatarfull", "")}
