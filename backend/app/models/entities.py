from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Float, Index, UniqueConstraint, func, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# JSON compatível com Postgres e SQLite (testes): usa JSON genérico.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Usuário")
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    profile: Mapped[Optional["CandidateProfile"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences: Mapped[Optional["SearchPreferences"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    favorites: Mapped[list["UserFavorite"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    feedbacks: Mapped[list["JobFeedback"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reports: Mapped[list["WeeklyReport"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    headline: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    seniority: Mapped[str] = mapped_column(String(32), default="mid")
    skills: Mapped[list] = mapped_column(JSONType, default=list)
    roles: Mapped[list] = mapped_column(JSONType, default=list)
    languages: Mapped[list] = mapped_column(JSONType, default=list)
    resume_file_path: Mapped[str] = mapped_column(String(512), default="")
    resume_text: Mapped[str] = mapped_column(Text, default="")

    user: Mapped["User"] = relationship(back_populates="profile")


class SearchPreferences(Base):
    __tablename__ = "search_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    desired_roles: Mapped[list] = mapped_column(JSONType, default=list)
    mandatory_keywords: Mapped[list] = mapped_column(JSONType, default=list)
    preferred_keywords: Mapped[list] = mapped_column(JSONType, default=list)
    excluded_keywords: Mapped[list] = mapped_column(JSONType, default=list)
    seniority_levels: Mapped[list] = mapped_column(JSONType, default=list)
    locations: Mapped[list] = mapped_column(JSONType, default=list)
    regions: Mapped[list] = mapped_column(JSONType, default=list)
    cities: Mapped[list] = mapped_column(JSONType, default=list)
    areas: Mapped[list] = mapped_column(JSONType, default=list)
    work_modes: Mapped[list] = mapped_column(JSONType, default=list)
    minimum_salary: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maximum_salary: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    employment_types: Mapped[list] = mapped_column(JSONType, default=list)
    preferred_companies: Mapped[list] = mapped_column(JSONType, default=list)
    excluded_companies: Mapped[list] = mapped_column(JSONType, default=list)
    excluded_jobs: Mapped[list] = mapped_column(JSONType, default=list)
    max_job_age_days: Mapped[int] = mapped_column(Integer, default=60)
    minimum_match_score: Mapped[int] = mapped_column(Integer, default=70)
    search_frequency_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled_sources: Mapped[list] = mapped_column(JSONType, default=list)
    telegram_enabled: Mapped[bool] = mapped_column(default=True)
    telegram_bot_token: Mapped[str] = mapped_column(String(128), default="")
    telegram_chat_id: Mapped[str] = mapped_column(String(64), default="")
    discord_enabled: Mapped[bool] = mapped_column(default=False)
    discord_webhook_url: Mapped[str] = mapped_column(String(512), default="")
    email_enabled: Mapped[bool] = mapped_column(default=False)
    email_digest_mode: Mapped[str] = mapped_column(String(16), default="immediately")

    user: Mapped["User"] = relationship(back_populates="preferences")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_jobs_content_hash"),
        UniqueConstraint("uuid", name="uq_jobs_uuid"),
        Index("ix_jobs_source", "source"),
        Index("ix_jobs_discovered", "discovered_at"),
        Index("ix_jobs_published", "published_at"),
        Index("ix_jobs_company", "company"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_uuid", "uuid"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()))
    external_id: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    title: Mapped[str] = mapped_column(String(255))
    normalized_title: Mapped[str] = mapped_column(String(255), default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    normalized_company: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    work_mode: Mapped[str] = mapped_column(String(32), default="")
    seniority: Mapped[str] = mapped_column(String(32), default="")
    employment_type: Mapped[str] = mapped_column(String(32), default="")
    area: Mapped[str] = mapped_column(String(128), default="Tecnologia")
    description: Mapped[str] = mapped_column(Text, default="")
    salary_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salary_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="BRL")
    requirements: Mapped[list] = mapped_column(JSONType, default=list)
    nice_to_have: Mapped[list] = mapped_column(JSONType, default=list)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_status: Mapped[str] = mapped_column(String(32), default="verified")  # "verified", "unknown_date"
    discovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")  # "active", "closed", "potential_ghost"
    status_reason: Mapped[str] = mapped_column(String(255), default="")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    alternative_sources: Mapped[list] = mapped_column(JSONType, default=list)
    raw_data: Mapped[dict] = mapped_column(JSONType, default=dict)

    changelogs: Mapped[list["JobChangelog"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobChangelog(Base):
    __tablename__ = "job_changelogs"
    __table_args__ = (
        Index("ix_changelog_job", "job_id"),
        Index("ix_changelog_job_field", "job_id", "field_name"),
        Index("ix_changelog_created", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    field_name: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(String(32))  # salary, work_mode, status, description, location
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notified: Mapped[bool] = mapped_column(default=False)

    job: Mapped["Job"] = relationship(back_populates="changelogs")


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("job_id", "profile_id", name="uq_job_match_profile"),
        Index("ix_match_score", "score"),
        Index("ix_match_job", "job_id"),
        Index("ix_match_profile", "profile_id")
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    score: Mapped[int] = mapped_column(Integer, default=0)
    skills_score: Mapped[int] = mapped_column(Integer, default=0)
    seniority_score: Mapped[int] = mapped_column(Integer, default=0)
    location_score: Mapped[int] = mapped_column(Integer, default=0)
    role_score: Mapped[int] = mapped_column(Integer, default=0)
    salary_score: Mapped[int] = mapped_column(Integer, default=0)
    reasoning: Mapped[list] = mapped_column(JSONType, default=list)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", "channel", name="uq_notifications_user_job_channel"),
        Index("ix_notif_user_status", "user_id", "status"),
        Index("ix_notif_job", "job_id"),
        Index("ix_notif_channel", "channel"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")


class SearchRun(Base):
    __tablename__ = "search_runs"
    __table_args__ = (
        Index("ix_run_started", "started_at"),
        Index("ix_run_status", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running, completed, partial_error, failed
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_count: Mapped[int] = mapped_column(Integer, default=0)
    discarded_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    notified_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONType, default=list)
    source_stats: Mapped[dict] = mapped_column(JSONType, default=dict)
    discard_reasons: Mapped[dict] = mapped_column(JSONType, default=dict)


class CircuitBreakerRecord(Base):
    __tablename__ = "circuit_breakers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(16), default="CLOSED")  # CLOSED, OPEN, HALF_OPEN
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(255), default="")


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_favorite"),
        Index("ix_fav_user", "user_id"),
        Index("ix_fav_job", "job_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    notes: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="favorites")
    job: Mapped["Job"] = relationship()


class JobFeedback(Base):
    __tablename__ = "job_feedbacks"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_feedback"),
        Index("ix_feedback_user", "user_id"),
        Index("ix_feedback_job", "job_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    is_positive: Mapped[bool] = mapped_column(Boolean, default=True)  # True = 👍, False = 👎
    feedback_type: Mapped[str] = mapped_column(String(32), default="relevant")
    comment: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="feedbacks")
    job: Mapped["Job"] = relationship()


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"
    __table_args__ = (
        Index("ix_weekly_user", "user_id"),
        Index("ix_weekly_created", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_jobs_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    total_compatible: Mapped[int] = mapped_column(Integer, default=0)
    total_new: Mapped[int] = mapped_column(Integer, default=0)
    total_remote: Mapped[int] = mapped_column(Integer, default=0)
    total_hybrid: Mapped[int] = mapped_column(Integer, default=0)
    total_onsite: Mapped[int] = mapped_column(Integer, default=0)
    total_internships: Mapped[int] = mapped_column(Integer, default=0)
    top_jobs: Mapped[list] = mapped_column(JSONType, default=list)
    presented_job_ids: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="reports")

