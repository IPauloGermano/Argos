from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./hermes.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    BACKEND_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000"
    ENVIRONMENT: str = "development"

    # AI / LLM
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_TIMEOUT_SECONDS: int = 30

    # Continuous Search & Scheduler
    ENABLE_BUILTIN_SCHEDULER: bool = True
    DEFAULT_SEARCH_FREQUENCY_MINUTES: int = 60
    MAX_CONCURRENT_SOURCE_CRAWLS: int = 4

    # Sources (indeed desativado: RSS descontinuado + busca com bloqueio anti-bot)
    JOB_SOURCES: str = "gupy,linkedin,remoteok,vagas,ciee,greenhouse,remotive"
    MOCK_JOBS_COUNT: int = 0
    SOURCE_TIMEOUT_SECONDS: int = 30
    SOURCE_MAX_PAGES: int = 5
    SOURCE_RATE_LIMIT_DELAY_SECONDS: float = 1.0

    # Browser fallback (CloakBrowser) para fontes com bloqueio anti-bot.
    # Apenas leitura de paginas publicas: sem login, sem formularios,
    # sem interacao com CAPTCHA. Desligue com CLOAK_ENABLED=false.
    CLOAK_ENABLED: bool = True
    CLOAK_HEADLESS: bool = True
    CLOAK_TIMEOUT_SECONDS: int = 45

    # Specific Source Settings
    REMOTIVE_TIMEOUT_SECONDS: int = 20
    GUPY_PORTAL_URL: str = "https://portal.gupy.io/api/v1/jobs"
    LINKEDIN_GUEST_API_URL: str = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    INDEED_SEARCH_URL: str = "https://br.indeed.com"
    VAGAS_BASE_URL: str = "https://www.vagas.com.br"
    CIEE_API_URL: str = "https://web.ciee.org.br"

    # Filtering, Deduplication & Validation
    MAX_JOB_AGE_DAYS: int = 60
    DEDUPLICATION_SIMILARITY_THRESHOLD: float = 0.88
    MINIMUM_MATCH_SCORE: int = 70
    VERIFY_JOB_URL_HEALTH: bool = False

    # Circuit Breakers
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 300

    # Matching Weights
    MATCH_WEIGHT_ROLE: float = 0.25
    MATCH_WEIGHT_SKILLS: float = 0.30
    MATCH_WEIGHT_SENIORITY: float = 0.15
    MATCH_WEIGHT_LOCATION: float = 0.10
    MATCH_WEIGHT_SALARY: float = 0.10
    MATCH_WEIGHT_OVERALL: float = 0.10

    # Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_TIMEOUT_SECONDS: int = 15

    DISCORD_WEBHOOK_URL: str = ""
    DISCORD_TIMEOUT_SECONDS: int = 15

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "hermes@localhost"
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT_SECONDS: int = 15


settings = Settings()

