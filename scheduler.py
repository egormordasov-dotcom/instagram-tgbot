import logging
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

async def sync_account(pool, account: dict):
    """Синхронизирует один аккаунт: обновляет видео, просмотры, матчи артикулов."""
    from instagram import collect_account, find_articles_in_text

    username   = account["username"]
    account_id = account["id"]
    logger.info(f"Синхронизируем @{username}...")

    try:
        ig_user_id, reels = await collect_account(username)
        if not reels:
            logger.warning(f"@{username}: Reels не получены")
            return

        async with pool.acquire() as conn:
            # Обновляем ig_user_id
            if ig_user_id:
                await conn.execute(
                    "UPDATE accounts SET ig_user_id=$1 WHERE id=$2",
                    ig_user_id, account_id
                )

            # Получаем все артикулы всех пользователей
            all_articles = await conn.fetch(
                "SELECT a.id, a.article, a.user_id FROM articles a "
                "JOIN accounts ac ON ac.user_id = a.user_id "
                "WHERE ac.id = $1",
                account_id
            )

            for reel in reels:
                # Upsert видео
                row = await conn.fetchrow("""
                    INSERT INTO videos (account_id, video_id, platform, title, description, published_at, views, updated_at)
                    VALUES ($1,$2,'instagram',$3,$4,$5,$6,NOW())
                    ON CONFLICT (account_id, video_id) DO UPDATE
                    SET views=EXCLUDED.views, title=EXCLUDED.title,
                        description=EXCLUDED.description, updated_at=NOW()
                    RETURNING id, views
                """, account_id, reel["video_id"], reel["title"],
                    reel["description"], reel["published_at"], reel["views"])

                video_db_id = row["id"]

                # Снимок просмотров
                await conn.execute(
                    "INSERT INTO snapshots (video_id, views) VALUES ($1,$2)",
                    video_db_id, reel["views"]
                )

                # Матчинг артикулов
                search_text = (reel["title"] or "") + "\n" + (reel["description"] or "")
                for art in all_articles:
                    found = find_articles_in_text(search_text, [art["article"]])
                    if found:
                        await conn.execute("""
                            INSERT INTO article_matches (article_id, video_id)
                            VALUES ($1,$2) ON CONFLICT DO NOTHING
                        """, art["id"], video_db_id)
                    else:
                        await conn.execute("""
                            DELETE FROM article_matches WHERE article_id=$1 AND video_id=$2
                        """, art["id"], video_db_id)

        logger.info(f"@{username}: синхронизировано {len(reels)} Reels")

    except Exception as e:
        logger.error(f"@{username}: ошибка синхронизации — {e}")

async def sync_all(pool):
    """Синхронизирует все активные аккаунты."""
    async with pool.acquire() as conn:
        accounts = await conn.fetch(
            "SELECT id, username FROM accounts WHERE is_active=TRUE AND platform='instagram'"
        )

    logger.info(f"Запуск синхронизации: {len(accounts)} аккаунтов")
    for account in accounts:
        await sync_account(pool, dict(account))
        await asyncio.sleep(2)

async def send_scheduled_reports(pool, bot):
    """Отправляет запланированные отчёты."""
    now_hour = datetime.now().hour
    async with pool.acquire() as conn:
        reports = await conn.fetch("""
            SELECT sr.user_id, sr.period
            FROM scheduled_reports sr
            WHERE sr.is_active=TRUE AND sr.send_hour=$1
        """, now_hour)

    for report in reports:
        try:
            from handlers.reports import build_summary_text
            text = await build_summary_text(pool, report["user_id"], report["period"])
            await bot.send_message(report["user_id"], text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Авто-отчёт для {report['user_id']}: {e}")
