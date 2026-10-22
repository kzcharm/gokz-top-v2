from datetime import datetime

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


class ScheduledTaskResult(SQLModel):
    processed: int
    created: int
    updated: int
    errors: int
    warnings: int = 0


class ScheduledTaskState(SQLModel, table=True):
    __tablename__ = "scheduled_task_state"

    task_name: str = Field(primary_key=True, max_length=100)
    last_started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_successful_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_error: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    cursor: int | None = None
    last_processed: int = 0
    last_created: int = 0
    last_updated: int = 0
    last_errors: int = 0
    last_warnings: int = 0
