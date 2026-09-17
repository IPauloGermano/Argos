from datetime import datetime
from sqlalchemy import DateTime, func
from app.core.database import Base


class TimestampMixin:
    created_at = DateTime(timezone=True, nullable=False, server_default=func.now())
    updated_at = DateTime(timezone=True, nullable=False, server_default=func.now(), onupdate=func.now())
