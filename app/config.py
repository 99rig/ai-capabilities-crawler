from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://crawler:crawler@postgres:5432/ai_capabilities"
    crawl_concurrency: int = 2
    crawl_batch_size: int = 1000
    crawl_workers: int = 300
    http_timeout: float = 3.0
    data_dir: str = "/data"
    dedup_found_hours: int = 24
    dedup_notfound_days: int = 7

    model_config = {"env_prefix": "CRAWL_"}


settings = Settings()
