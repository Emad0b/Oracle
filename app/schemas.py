from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    model: str
    needs_confirmation: bool = False


class GoogleStatusResponse(BaseModel):
    configured: bool
    connected: bool
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    can_read_mail: bool = False
    can_send_mail: bool = False
    can_use_calendar: bool = False
