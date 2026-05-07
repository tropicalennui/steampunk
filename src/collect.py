"""Thin shim — all logic lives in src/collectors/.

Re-exports every public name so existing imports (e.g. `from collect import stage_xbox`)
and test patches (e.g. `patch("collect.requests.post")`) continue to work unchanged.
"""
import requests  # noqa: F401 — must be importable as collect.requests for test patches

from collectors import (  # noqa: F401
    make_read_session, validate_session_cookie,
    fetch_library, fetch_app_details, fetch_achievements, fetch_wishlist,
    stage, promote,
    refresh_gog_token, fetch_gog_library, fetch_gog_product,
    stage_gog, promote_gog,
    exchange_npsso_for_tokens, refresh_psn_token, fetch_psn_trophy_titles,
    stage_psn, promote_psn,
    fetch_switch_devices, fetch_switch_library,
    stage_switch, promote_switch,
    fetch_xbox_library,
    stage_xbox, promote_xbox,
    get_igdb_token, igdb_lookup_by_external_id,
    run_igdb_matching, run_store_availability,
    PLATFORM_STEAM, PLATFORM_PSN, PLATFORM_GOG, PLATFORM_SWITCH, PLATFORM_XBOX,
    IGDB_STEAM_CATEGORY, IGDB_GOG_CATEGORY, IGDB_PSN_CATEGORY,
    run,
)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["steam", "gog", "psn", "switch", "xbox"],
        default=["steam", "gog", "psn", "switch", "xbox"],
        help="Which platform libraries to sync (default: all)",
    )
    args = parser.parse_args()
    run(platforms=set(args.platforms))
