import structlog

from app.database import get_background_session_factory
from app.services.arbitrage_service import ArbitrageService
from app.services.matching_service import MatchingService

logger = structlog.get_logger()


async def run_matching() -> None:
    logger.info("run_matching_started")

    async with get_background_session_factory()() as db:
        try:
            matching_service = MatchingService(db)
            new_pairs = await matching_service.run_matching()

            arbitrage_service = ArbitrageService(db)
            updated_deltas = await arbitrage_service.update_deltas()

            await db.commit()
            logger.info(
                "run_matching_complete",
                new_pairs=new_pairs,
                updated_deltas=updated_deltas,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("run_matching_failed", error=str(exc), exc_info=True)
