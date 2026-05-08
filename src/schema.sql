-- =============================================================================
-- SteamPunk Schema
-- DB file: steampunk.duckdb (root, gitignored)
-- Pattern: stg_* = raw source data per platform
--          canonical tables = normalised, cross-platform layer
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Lookup tables
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS platforms (
    id           INTEGER PRIMARY KEY,
    slug         VARCHAR NOT NULL UNIQUE,   -- 'steam' | 'psn' | 'gog' | 'switch'
    display_name VARCHAR NOT NULL
);

INSERT OR IGNORE INTO platforms VALUES
    (1, 'steam',  'Steam'),
    (2, 'psn',    'PlayStation Network'),
    (3, 'gog',    'GOG'),
    (4, 'switch', 'Nintendo Switch'),
    (5, 'xbox',   'Xbox');

CREATE SEQUENCE IF NOT EXISTS seq_tags START 1;

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY DEFAULT nextval('seq_tags'),
    name VARCHAR NOT NULL UNIQUE
);

CREATE SEQUENCE IF NOT EXISTS seq_genres START 1;

CREATE TABLE IF NOT EXISTS genres (
    id   INTEGER PRIMARY KEY DEFAULT nextval('seq_genres'),
    name VARCHAR NOT NULL UNIQUE
);


-- -----------------------------------------------------------------------------
-- Canonical games
-- -----------------------------------------------------------------------------

CREATE SEQUENCE IF NOT EXISTS seq_games START 1;

CREATE TABLE IF NOT EXISTS games (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_games'),
    title       VARCHAR NOT NULL,
    cover_url   VARCHAR,
    igdb_id     INTEGER,           -- nullable, used for cross-platform dedup later
    merged_into INTEGER REFERENCES games(id)  -- set when this row is merged into another
);

ALTER TABLE games ADD COLUMN IF NOT EXISTS merged_into INTEGER;

-- Platform-specific record for a game (one row per platform the game exists on)
CREATE SEQUENCE IF NOT EXISTS seq_platform_games START 1;

CREATE TABLE IF NOT EXISTS platform_games (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_platform_games'),
    platform_id INTEGER NOT NULL REFERENCES platforms(id),
    external_id VARCHAR NOT NULL,   -- Steam app_id, PSN product id, GOG id, etc.
    game_id     INTEGER REFERENCES games(id),  -- nullable until canonically linked
    UNIQUE (platform_id, external_id)
);

-- Junctions
CREATE TABLE IF NOT EXISTS game_tags (
    game_id INTEGER NOT NULL REFERENCES games(id),
    tag_id  INTEGER NOT NULL REFERENCES tags(id),
    PRIMARY KEY (game_id, tag_id)
);

CREATE TABLE IF NOT EXISTS game_genres (
    game_id  INTEGER NOT NULL REFERENCES games(id),
    genre_id INTEGER NOT NULL REFERENCES genres(id),
    PRIMARY KEY (game_id, genre_id)
);


-- -----------------------------------------------------------------------------
-- User data (canonical)
-- -----------------------------------------------------------------------------

CREATE SEQUENCE IF NOT EXISTS seq_library START 1;

CREATE TABLE IF NOT EXISTS library (
    id               INTEGER PRIMARY KEY DEFAULT nextval('seq_library'),
    platform_game_id INTEGER   NOT NULL UNIQUE REFERENCES platform_games(id),
    playtime_mins    INTEGER   NOT NULL DEFAULT 0,
    last_played_at   TIMESTAMP,
    never_launched   BOOLEAN   NOT NULL DEFAULT FALSE,
    collected_at     TIMESTAMP NOT NULL DEFAULT current_timestamp
);

ALTER TABLE library ADD COLUMN IF NOT EXISTS purchased_at     DATE;
ALTER TABLE library ADD COLUMN IF NOT EXISTS purchase_source VARCHAR;
ALTER TABLE library ADD COLUMN IF NOT EXISTS first_played_at  TIMESTAMP;

CREATE SEQUENCE IF NOT EXISTS seq_wishlist START 1;

CREATE TABLE IF NOT EXISTS wishlist (
    id               INTEGER PRIMARY KEY DEFAULT nextval('seq_wishlist'),
    platform_game_id INTEGER   NOT NULL UNIQUE REFERENCES platform_games(id),
    added_at         TIMESTAMP,
    collected_at     TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE SEQUENCE IF NOT EXISTS seq_achievements START 1;

CREATE TABLE IF NOT EXISTS achievements (
    id               INTEGER PRIMARY KEY DEFAULT nextval('seq_achievements'),
    platform_game_id INTEGER NOT NULL UNIQUE REFERENCES platform_games(id),
    unlocked_count   INTEGER NOT NULL DEFAULT 0,
    total_count      INTEGER NOT NULL DEFAULT 0,
    completion_pct   DOUBLE  NOT NULL DEFAULT 0.0,
    collected_at     TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE SEQUENCE IF NOT EXISTS seq_reviews START 1;

CREATE TABLE IF NOT EXISTS reviews (
    id               INTEGER PRIMARY KEY DEFAULT nextval('seq_reviews'),
    platform_game_id INTEGER   NOT NULL UNIQUE REFERENCES platform_games(id),
    review_text      VARCHAR,
    collected_at     TIMESTAMP NOT NULL DEFAULT current_timestamp
);


-- -----------------------------------------------------------------------------
-- Staging: Steam
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stg_steam_library (
    app_id               INTEGER   PRIMARY KEY,
    name                 VARCHAR,
    playtime_forever_mins INTEGER  NOT NULL DEFAULT 0,
    playtime_2weeks_mins  INTEGER,
    last_played_at       TIMESTAMP,
    collected_at         TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS stg_steam_app_details (
    app_id               INTEGER   PRIMARY KEY,
    name                 VARCHAR,
    genres               VARCHAR[],
    tags                 VARCHAR[],
    categories           VARCHAR[],
    content_descriptors  VARCHAR[],
    header_image         VARCHAR,
    release_date         VARCHAR,
    collected_at         TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS stg_steam_achievements (
    app_id          INTEGER   PRIMARY KEY,
    unlocked_count  INTEGER   NOT NULL DEFAULT 0,
    total_count     INTEGER   NOT NULL DEFAULT 0,
    completion_pct  DOUBLE    NOT NULL DEFAULT 0.0,
    collected_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS stg_steam_wishlist (
    app_id       INTEGER   PRIMARY KEY,
    added_at     TIMESTAMP,
    collected_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS stg_steam_reviews (
    app_id       INTEGER   PRIMARY KEY,
    review_text  VARCHAR,
    collected_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);


-- -----------------------------------------------------------------------------
-- Staging: GOG
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stg_gog_library (
    product_id   VARCHAR   PRIMARY KEY,
    title        VARCHAR,
    cover_url    VARCHAR,
    release_date DATE,
    collected_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);


-- -----------------------------------------------------------------------------
-- Staging: PSN
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stg_psn_library (
    np_communication_id  VARCHAR   PRIMARY KEY,
    title                VARCHAR,
    cover_url            VARCHAR,
    platform             VARCHAR,         -- 'PS4' or 'PS5'
    acquisition_type     VARCHAR,         -- 'purchased', 'subscription', or NULL (unknown)
    trophy_progress      INTEGER,         -- 0-100 completion %
    trophies_earned      INTEGER,
    trophies_defined     INTEGER,
    collected_at         TIMESTAMP NOT NULL DEFAULT current_timestamp
);


-- -----------------------------------------------------------------------------
-- Staging: Nintendo Switch
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stg_switch_library (
    ns_uid          VARCHAR   PRIMARY KEY,
    title           VARCHAR   NOT NULL,
    image_url       VARCHAR,
    play_time_mins  INTEGER   NOT NULL DEFAULT 0,
    collected_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
);


-- -----------------------------------------------------------------------------
-- Staging: Xbox
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stg_xbox_library (
    title_id            VARCHAR   PRIMARY KEY,
    title               VARCHAR,
    last_played         TIMESTAMP,
    achievements_earned INTEGER,
    achievements_total  INTEGER,
    gamerscore_earned   INTEGER,
    gamerscore_total    INTEGER,
    collected_at        TIMESTAMP NOT NULL DEFAULT current_timestamp
);

ALTER TABLE achievements ADD COLUMN IF NOT EXISTS gamerscore_earned INTEGER;
ALTER TABLE achievements ADD COLUMN IF NOT EXISTS gamerscore_total  INTEGER;


-- -----------------------------------------------------------------------------
-- Cross-platform store availability
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS store_availability (
    game_id     INTEGER   NOT NULL REFERENCES games(id),
    platform_id INTEGER   NOT NULL REFERENCES platforms(id),
    available   BOOLEAN   NOT NULL,
    external_id VARCHAR,
    checked_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (game_id, platform_id)
);


-- -----------------------------------------------------------------------------
-- User preferences (ratings, hidden) — keyed on canonical game, not platform
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_game_prefs (
    game_id    INTEGER   PRIMARY KEY REFERENCES games(id),
    rating     VARCHAR   CHECK (rating IN ('up', 'down')),
    hidden     BOOLEAN   NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
