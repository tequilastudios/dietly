from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dietly"

    db_host: str = "db"
    db_port: int = 3306
    db_name: str = "dietly"
    db_user: str = "dietly"
    db_password: str = "dietlypass"

    jwt_secret: str = "super-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llava:latest"
    ollama_text_model: str = "mistral:latest"
    ollama_timeout: int = 180

    upload_dir: str = "/app/static/uploads"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
