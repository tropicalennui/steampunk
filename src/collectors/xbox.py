import asyncio
import json
from datetime import UTC, datetime
from typing import Optional

import duckdb

from db import SECRETS_PATH
from collectors.pipeline import _write_secrets


# ---------------------------------------------------------------------------
# Fetch (async, bridged to sync via asyncio.run)
# ---------------------------------------------------------------------------

async def _xbox_fetch_async(  # pragma: no cover
    client_id: str,
    oauth_dict: dict,
    xau_dict: dict,
    xsts_dict: dict,
) -> tuple[list, dict, dict, dict]:
    from xbox.webapi.authentication.manager import AuthenticationManager
    from xbox.webapi.authentication.models import OAuth2TokenResponse, XAUResponse, XSTSResponse
    from xbox.webapi.api.client import XboxLiveClient
    from xbox.webapi.api.provider.titlehub.models import TitleFields
    from xbox.webapi.common.signed_session import SignedSession

    async with SignedSession() as session:
        auth_mgr = AuthenticationManager(session, client_id, "", "")
        auth_mgr.oauth       = OAuth2TokenResponse(**oauth_dict)
        auth_mgr.user_token  = XAUResponse(**xau_dict)
        auth_mgr.xsts_token  = XSTSResponse(**xsts_dict)

        await auth_mgr.refresh_tokens()

        client = XboxLiveClient(auth_mgr)
        xuid   = auth_mgr.xsts_token.xuid

        # The Xbox API returns null for several fields (displayImage, mediaItemType,
        # isBundle) that the library's strict pydantic model rejects. Bind a
        # replacement method that sanitises nulls before parsing.
        import types
        from xbox.webapi.api.provider.titlehub.models import TitleHubResponse as _THR

        async def _lenient_get_title_history(self, xuid, fields=None, max_items=5, **kwargs):
            if not fields:
                from xbox.webapi.api.provider.titlehub.models import TitleFields as TF
                fields = [TF.ACHIEVEMENT, TF.IMAGE, TF.SERVICE_CONFIG_ID]
            fields_str = self.SEPARATOR.join(
                f.value if hasattr(f, "value") else f for f in fields
            )
            url  = f"{self.TITLEHUB_URL}/users/xuid({xuid})/titles/titlehistory/decoration/{fields_str}"
            resp = await self.client.session.get(
                url, params={"maxItems": max_items}, headers=self._headers, **kwargs
            )
            resp.raise_for_status()
            data         = resp.json()
            null_defaults = {"displayImage": "", "mediaItemType": "", "isBundle": False}
            for title in data.get("titles", []):
                for field, default in null_defaults.items():
                    if title.get(field) is None:
                        title[field] = default
            return _THR(**data)

        client.titlehub.get_title_history = types.MethodType(
            _lenient_get_title_history, client.titlehub
        )

        response = await client.titlehub.get_title_history(
            xuid=xuid,
            fields=[TitleFields.ACHIEVEMENT],
            max_items=2000,
        )

        return (
            response.titles,
            auth_mgr.oauth.model_dump(mode="json"),
            auth_mgr.user_token.model_dump(mode="json"),
            auth_mgr.xsts_token.model_dump(mode="json"),
        )


def fetch_xbox_library(secrets: dict) -> Optional[list]:  # pragma: no cover
    xbox_cfg   = secrets.get("xbox", {})
    client_id  = xbox_cfg.get("client_id")
    oauth_dict = xbox_cfg.get("oauth")
    xau_dict   = xbox_cfg.get("user_token")
    xsts_dict  = xbox_cfg.get("xsts_token")

    if not all([client_id, oauth_dict, xau_dict, xsts_dict]):
        return None

    titles, oauth, xau, xsts = asyncio.run(
        _xbox_fetch_async(client_id, oauth_dict, xau_dict, xsts_dict)
    )

    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("xbox", {}).update({"oauth": oauth, "user_token": xau, "xsts_token": xsts})
    _write_secrets(persisted)

    return titles


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

def stage_xbox(conn: duckdb.DuckDBPyConnection, titles: list) -> None:
    if not titles:
        return
    now  = datetime.now(UTC)
    rows = []
    for t in titles:
        ach  = t.achievement
        hist = t.title_history
        rows.append((
            str(t.title_id),
            t.name,
            hist.last_time_played if hist else None,
            ach.current_achievements if ach else None,
            ach.total_achievements   if ach else None,
            ach.current_gamerscore   if ach else None,
            ach.total_gamerscore     if ach else None,
            now,
        ))
    conn.executemany(
        """
        INSERT INTO stg_xbox_library
            (title_id, title, last_played, achievements_earned, achievements_total,
             gamerscore_earned, gamerscore_total, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (title_id) DO UPDATE SET
            title               = excluded.title,
            last_played         = excluded.last_played,
            achievements_earned = excluded.achievements_earned,
            achievements_total  = excluded.achievements_total,
            gamerscore_earned   = excluded.gamerscore_earned,
            gamerscore_total    = excluded.gamerscore_total,
            collected_at        = excluded.collected_at
        """,
        rows,
    )


# ---------------------------------------------------------------------------
# Promote staging → canonical
# ---------------------------------------------------------------------------

def promote_xbox(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        INSERT INTO games (title)
        SELECT sg.title
        FROM stg_xbox_library sg
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 5 AND pg.external_id = sg.title_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM games g WHERE g.title = sg.title
        )
    """)

    conn.execute("""
        INSERT INTO platform_games (platform_id, external_id, game_id)
        SELECT 5, sg.title_id, g.id
        FROM stg_xbox_library sg
        JOIN games g ON g.title = sg.title
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 5 AND pg.external_id = sg.title_id
        )
        ON CONFLICT DO NOTHING
    """)

    conn.execute("""
        INSERT INTO library
            (platform_game_id, playtime_mins, last_played_at, never_launched,
             purchase_source, collected_at)
        SELECT
            pg.id,
            0,
            sg.last_played,
            (sg.last_played IS NULL),
            'unknown',
            sg.collected_at
        FROM stg_xbox_library sg
        JOIN platform_games pg
          ON pg.platform_id = 5 AND pg.external_id = sg.title_id
        ON CONFLICT (platform_game_id) DO UPDATE SET
            last_played_at = excluded.last_played_at,
            never_launched = excluded.never_launched,
            collected_at   = excluded.collected_at
    """)

    conn.execute("""
        INSERT INTO achievements
            (platform_game_id, unlocked_count, total_count, completion_pct,
             gamerscore_earned, gamerscore_total, collected_at)
        SELECT
            pg.id,
            COALESCE(sg.achievements_earned, 0),
            COALESCE(sg.achievements_total, 0),
            CASE WHEN COALESCE(sg.achievements_total, 0) > 0
                 THEN CAST(sg.achievements_earned AS DOUBLE) / sg.achievements_total * 100
                 ELSE 0.0
            END,
            sg.gamerscore_earned,
            sg.gamerscore_total,
            sg.collected_at
        FROM stg_xbox_library sg
        JOIN platform_games pg
          ON pg.platform_id = 5 AND pg.external_id = sg.title_id
        WHERE COALESCE(sg.achievements_total, 0) > 0
        ON CONFLICT (platform_game_id) DO UPDATE SET
            unlocked_count    = excluded.unlocked_count,
            total_count       = excluded.total_count,
            completion_pct    = excluded.completion_pct,
            gamerscore_earned = excluded.gamerscore_earned,
            gamerscore_total  = excluded.gamerscore_total,
            collected_at      = excluded.collected_at
    """)


# ---------------------------------------------------------------------------
# Sync helper
# ---------------------------------------------------------------------------

def _sync_xbox(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:  # pragma: no cover
    xbox_cfg = secrets.get("xbox", {})
    if not xbox_cfg.get("oauth"):
        print("\nXbox not connected — skipping Xbox sync")
        return
    if xbox_cfg.get("auth_expired"):
        print("\nXbox session expired — reconnect via Setup page")
        return

    print("\nFetching Xbox library...")
    try:
        titles = fetch_xbox_library(secrets)
    except Exception as exc:
        import traceback
        import httpx
        print(f"  Xbox sync failed: {exc}")
        print(traceback.format_exc())
        is_auth_error = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401
        if is_auth_error:
            with open(SECRETS_PATH) as f:
                persisted = json.load(f)
            persisted.setdefault("xbox", {})["auth_expired"] = True
            _write_secrets(persisted)
            print("  Xbox session expired — reconnect via Setup page")
        return

    if titles is None:
        print("  Xbox credentials incomplete — skipping Xbox sync")
        return

    print(f"  {len(titles)} Xbox titles found")
    print("Staging Xbox data...")
    stage_xbox(conn, titles)
    print("Promoting Xbox data to canonical tables...")
    promote_xbox(conn)
