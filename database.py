import asyncpg
import os

async def get_pool():
    return await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=5)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          BIGINT PRIMARY KEY,
            username    TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id          SERIAL PRIMARY KEY,
            user_id     BIGINT REFERENCES users(id),
            platform    TEXT NOT NULL DEFAULT 'instagram',
            username    TEXT NOT NULL,
            ig_user_id  TEXT,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, platform, username)
        );

        CREATE TABLE IF NOT EXISTS videos (
            id           SERIAL PRIMARY KEY,
            account_id   INT REFERENCES accounts(id),
            video_id     TEXT NOT NULL,
            platform     TEXT NOT NULL DEFAULT 'instagram',
            title        TEXT,
            description  TEXT,
            published_at TIMESTAMPTZ,
            views        BIGINT DEFAULT 0,
            updated_at   TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(account_id, video_id)
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id          SERIAL PRIMARY KEY,
            video_id    INT REFERENCES videos(id),
            views       BIGINT NOT NULL,
            taken_at    TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS articles (
            id          SERIAL PRIMARY KEY,
            user_id     BIGINT REFERENCES users(id),
            article     TEXT NOT NULL,
            name        TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, article)
        );

        CREATE TABLE IF NOT EXISTS article_matches (
            article_id  INT REFERENCES articles(id) ON DELETE CASCADE,
            video_id    INT REFERENCES videos(id)   ON DELETE CASCADE,
            PRIMARY KEY (article_id, video_id)
        );

        CREATE TABLE IF NOT EXISTS scheduled_reports (
            id          SERIAL PRIMARY KEY,
            user_id     BIGINT REFERENCES users(id),
            period      TEXT NOT NULL,
            send_hour   INT  DEFAULT 9,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, period)
        );

        CREATE INDEX IF NOT EXISTS idx_videos_account    ON videos(account_id);
        CREATE INDEX IF NOT EXISTS idx_videos_published  ON videos(published_at);
        CREATE INDEX IF NOT EXISTS idx_snapshots_video   ON snapshots(video_id, taken_at);
        CREATE INDEX IF NOT EXISTS idx_matches_article   ON article_matches(article_id);
        """)
