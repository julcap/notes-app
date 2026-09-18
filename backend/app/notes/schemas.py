from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default='', max_length=100000)
    attendees: str = Field(default='', max_length=1000)
    meeting_date: date
    scheduled_at: datetime | None = None

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Title cannot be blank')
        return value.strip()

    @field_validator('scheduled_at')
    @classmethod
    def scheduled_time_is_timezone_aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('Scheduled time must include a timezone')
        return value.astimezone(timezone.utc) if value is not None else None


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    size: int
    content_type: str


class ActionItemInput(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    owner_name: str = Field(default='', max_length=200)
    due_date: date | None = None

    @field_validator('text')
    @classmethod
    def text_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Text cannot be blank')
        return value.strip()


class ActionItemPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    owner_name: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    done: bool | None = None

    @field_validator('text')
    @classmethod
    def text_not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Text cannot be blank')
        return value.strip() if value is not None else value


class ActionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    text: str
    owner_name: str
    due_date: date | None
    done: bool
    created_at: datetime


class NoteOut(NoteInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime
    attachments: list[AttachmentOut]
    action_items: list[ActionItemOut]


class NotePage(BaseModel):
    items: list[NoteOut]
    total: int
