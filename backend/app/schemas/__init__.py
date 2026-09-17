from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    telegram_chat_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class ProfileOut(BaseModel):
    id: int
    user_id: int
    headline: str = ""
    summary: str = ""
    years_experience: int = 0
    seniority: str = "mid"
    skills: list[str] = []
    roles: list[str] = []
    languages: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    years_experience: Optional[int] = None
    seniority: Optional[str] = None
    skills: Optional[list[str]] = None
    roles: Optional[list[str]] = None
    languages: Optional[list[str]] = None


class PreferencesOut(BaseModel):
    id: int
    user_id: int
    desired_roles: list[str] = []
    mandatory_keywords: list[str] = []
    preferred_keywords: list[str] = []
    excluded_keywords: list[str] = []
    seniority_levels: list[str] = []
    locations: list[str] = []
    regions: list[str] = []
    cities: list[str] = []
    areas: list[str] = []
    work_modes: list[str] = []
    minimum_salary: Optional[float] = None
    min_salary: Optional[float] = None
    maximum_salary: Optional[float] = None
    max_salary: Optional[float] = None
    employment_types: list[str] = []
    preferred_companies: list[str] = []
    excluded_companies: list[str] = []
    max_job_age_days: int = 60
    minimum_match_score: int = 70
    search_frequency_minutes: int = 60
    enabled_sources: list[str] = []
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    email_enabled: bool = False
    email_digest_mode: str = "immediately"

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def populate_salary_aliases(self) -> PreferencesOut:
        if self.min_salary is None and self.minimum_salary is not None:
            self.min_salary = self.minimum_salary
        elif self.minimum_salary is None and self.min_salary is not None:
            self.minimum_salary = self.min_salary
        if self.max_salary is None and self.maximum_salary is not None:
            self.max_salary = self.maximum_salary
        elif self.maximum_salary is None and self.max_salary is not None:
            self.maximum_salary = self.max_salary
        return self


class PreferencesUpdate(BaseModel):
    desired_roles: Optional[list[str]] = None
    mandatory_keywords: Optional[list[str]] = None
    preferred_keywords: Optional[list[str]] = None
    excluded_keywords: Optional[list[str]] = None
    seniority_levels: Optional[list[str]] = None
    locations: Optional[list[str]] = None
    regions: Optional[list[str]] = None
    cities: Optional[list[str]] = None
    areas: Optional[list[str]] = None
    work_modes: Optional[list[str]] = None
    minimum_salary: Optional[float] = None
    min_salary: Optional[float] = None
    maximum_salary: Optional[float] = None
    max_salary: Optional[float] = None
    employment_types: Optional[list[str]] = None
    preferred_companies: Optional[list[str]] = None
    excluded_companies: Optional[list[str]] = None
    max_job_age_days: Optional[int] = Field(default=None, ge=1, le=365)
    minimum_match_score: Optional[int] = Field(default=None, ge=0, le=100)
    search_frequency_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    enabled_sources: Optional[list[str]] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_enabled: Optional[bool] = None
    discord_webhook_url: Optional[str] = None
    email_enabled: Optional[bool] = None
    email_digest_mode: Optional[str] = None


class JobChangelogOut(BaseModel):
    id: int
    job_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    change_type: str
    created_at: datetime
    notified: bool

    model_config = ConfigDict(from_attributes=True)


class JobOut(BaseModel):
    id: int
    uuid: str = ""
    source: str
    url: str
    title: str
    company: str
    location: str
    work_mode: str
    seniority: str
    employment_type: str
    area: str = "Tecnologia"
    description: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: str = "BRL"
    published_at: Optional[datetime] = None
    date_status: str = "verified"
    status: str = "active"
    status_reason: str = ""
    alternative_sources: list[dict] = []
    score: Optional[int] = None
    reasoning: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class SearchRunOut(BaseModel):
    id: int
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    pages_crawled: int = 0
    jobs_found: int = 0
    valid_count: int = 0
    duplicates_count: int = 0
    discarded_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    notified_count: int = 0
    errors: list[str] = []
    source_stats: dict = {}
    discard_reasons: dict = {}

    model_config = ConfigDict(from_attributes=True)


class CircuitBreakerOut(BaseModel):
    source_name: str
    state: str
    failure_count: int
    success_count: int
    last_failure_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    last_error: str = ""

    model_config = ConfigDict(from_attributes=True)


class AgentStatus(BaseModel):
    running: bool
    last_search: Optional[str] = None
    next_search: Optional[str] = None
    frequency_minutes: int = 60
    sources: list[str] = []
    last_stats: dict = {}
    circuit_breakers: list[CircuitBreakerOut] = []
