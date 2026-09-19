from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    max_upload_mb: int = 20
    max_input_width: int = 6000
    max_input_height: int = 6000

    max_output_width: int = 10000
    max_output_height: int = 10000
    max_output_pixels: int = 50_000_000

    job_ttl_minutes: int = 60
    max_ai_workers: int = 1
    poll_interval_ms: int = 1500

    upscale_tile_size: int = 512
    upscale_tile_overlap: int = 16

    rate_limit_per_minute: int = 10

    temp_root: str = "/tmp/image-lab"

    models_dir: str = "/app/models"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
