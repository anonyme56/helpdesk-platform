from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Status = Literal["open", "in_progress", "resolved", "closed"]
Priority = Literal["low", "normal", "high", "urgent"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (type de jeton OAuth2, pas un secret)


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: str


class RoleIn(BaseModel):
    role: Literal["user", "agent", "admin"]


class TicketIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: Priority = "normal"


class TicketPatch(BaseModel):
    status: Status | None = None
    priority: Priority | None = None
    assignee_id: int | None = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)


class CommentOut(ORM):
    id: int
    author: UserOut
    body: str
    created_at: datetime


class AttachmentOut(ORM):
    id: int
    filename: str
    content_type: str
    size: int
    created_at: datetime


class TicketOut(ORM):
    id: int
    title: str
    description: str
    status: str
    priority: str
    author: UserOut
    assignee: UserOut | None
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketOut):
    comments: list[CommentOut]
    attachments: list[AttachmentOut]


class ExportOut(ORM):
    id: int
    status: str
    created_at: datetime
    finished_at: datetime | None
    error: str | None = None
