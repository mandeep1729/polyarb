from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://polyarb:polyarb@localhost:5433/polyarb"
    REDIS_URL: str = "redis://localhost:6380"

    POLYMARKET_API_URL: str = "https://gamma-api.polymarket.com"
    POLYMARKET_CLOB_URL: str = "https://clob.polymarket.com"
    POLYMARKET_WS_URL: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    KALSHI_API_URL: str = "https://api.elections.kalshi.com/trade-api/v2"

    CORS_ORIGINS: list[str] = ["http://localhost:3001", "http://192.168.86.31:3001"]
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "/app/logs"

    FETCH_MARKETS_INTERVAL_SECONDS: int = 900
    FETCH_PRICES_INTERVAL_SECONDS: int = 3600
    MATCH_MARKETS_INTERVAL_SECONDS: int = 900
    CLEANUP_INTERVAL_SECONDS: int = 3600
    GROUP_MARKETS_INTERVAL_SECONDS: int = 600
    GROUP_FULL_REGROUP_INTERVAL_SECONDS: int = 7200
    GROUP_MERGE_THRESHOLD: float = 0.80
    GROUP_END_DATE_GATE_DAYS: float = 1.0
    BACKFILL_PRICES_INTERVAL_SECONDS: int = 86400
    PRICE_SYNC_TOP_N_GROUPS: int = 100
    BACKFILL_TOP_N_MARKETS: int = 1000
    SQL_ECHO: bool = True

    QDRANT_ENDPOINT: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    QDRANT_COLLECTION: str = "market_embeddings"
    EMBEDDING_MATCH_THRESHOLD: float = 0.75

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
