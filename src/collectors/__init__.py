from collectors.steam   import (
    make_read_session, validate_session_cookie,
    fetch_library, fetch_app_details, fetch_achievements, fetch_wishlist,
    stage, promote,
)
from collectors.gog     import (
    refresh_gog_token, fetch_gog_library, fetch_gog_product,
    stage_gog, promote_gog,
)
from collectors.psn     import (
    exchange_npsso_for_tokens, refresh_psn_token, fetch_psn_trophy_titles,
    stage_psn, promote_psn,
)
from collectors.switch  import (
    fetch_switch_devices, fetch_switch_library,
    stage_switch, promote_switch,
)
from collectors.xbox    import (
    fetch_xbox_library,
    stage_xbox, promote_xbox,
)
from collectors.igdb    import (
    get_igdb_token, igdb_lookup_by_external_id,
    run_igdb_matching, run_store_availability,
)
from collectors.pipeline import (
    PLATFORM_STEAM, PLATFORM_PSN, PLATFORM_GOG, PLATFORM_SWITCH, PLATFORM_XBOX,
    IGDB_STEAM_CATEGORY, IGDB_GOG_CATEGORY, IGDB_PSN_CATEGORY,
)

from collectors.steam   import _sync_steam, _sync_steam_library, _sync_steam_achievements, _sync_steam_wishlist
from collectors.gog     import _sync_gog
from collectors.psn     import _sync_psn
from collectors.switch  import _sync_switch
from collectors.xbox    import _sync_xbox
from collectors.igdb    import _sync_igdb

from db import connect, init_db, load_secrets


def _run_steam(conn, secrets: dict, platforms: set[str]) -> None:  # pragma: no cover
    steam_tokens = {p for p in platforms if p == "steam" or p.startswith("steam:")}
    if not steam_tokens:
        print("Skipping Steam sync (not selected)")
        return
    if "steam" in steam_tokens:
        _sync_steam(conn, secrets)
        return
    if "steam:library" in steam_tokens:
        _sync_steam_library(conn, secrets)
    if "steam:achievements" in steam_tokens:
        _sync_steam_achievements(conn, secrets)
    if "steam:wishlist" in steam_tokens:
        _sync_steam_wishlist(conn, secrets)


def run(platforms: set[str] = {"steam", "gog", "psn", "switch", "xbox", "igdb"}) -> None:  # pragma: no cover
    secrets = load_secrets()
    init_db()
    conn = connect()

    _run_steam(conn, secrets, platforms)

    if "gog" in platforms:
        _sync_gog(conn, secrets)
    else:
        print("\nSkipping GOG sync (not selected)")

    if "psn" in platforms:
        _sync_psn(conn, secrets)
    else:
        print("\nSkipping PSN sync (not selected)")

    if "switch" in platforms:
        _sync_switch(conn, secrets)
    else:
        print("\nSkipping Switch sync (not selected)")

    if "xbox" in platforms:
        _sync_xbox(conn, secrets)
    else:
        print("\nSkipping Xbox sync (not selected)")

    if "igdb" in platforms:
        _sync_igdb(conn, secrets)
    else:
        print("\nSkipping IGDB sync (not selected)")

    conn.close()
    print("\nAll done.")


if __name__ == "__main__":  # pragma: no cover
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["steam", "steam:library", "steam:achievements", "steam:wishlist",
                 "gog", "psn", "switch", "xbox", "igdb"],
        default=["steam", "gog", "psn", "switch", "xbox", "igdb"],
        help="Which platform libraries to sync (default: all)",
    )
    args = parser.parse_args()
    run(platforms=set(args.platforms))
