from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .models import TaskStatus, TaskType, TicketKind, TicketStatus, UserRole


class RegisterRequest(BaseModel):
    challenge_id: str = Field(min_length=36, max_length=36)
    phone_number: str = Field(min_length=11, max_length=18)
    verify_code: str = Field(pattern=r"^[0-9]{4,8}$")
    password: str = Field(min_length=8, max_length=128)
    accepted_terms: bool


class LoginRequest(BaseModel):
    identifier: str | None = Field(default=None, min_length=3, max_length=320)
    email: EmailStr | None = None
    password: str

    @model_validator(mode="after")
    def require_identifier(self) -> "LoginRequest":
        if not self.identifier and not self.email:
            raise ValueError("login identifier is required")
        return self

    @property
    def login_identifier(self) -> str:
        return self.identifier or str(self.email)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None
    role: UserRole
    available_points: int
    reserved_points: int
    phone_verified: bool
    phone_masked: str | None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class PhoneSendRequest(BaseModel):
    phone_number: str = Field(min_length=11, max_length=18)


class PhoneSendResponse(BaseModel):
    challenge_id: str
    expires_in: int
    resend_after: int


class PhoneVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=36, max_length=36)
    phone_number: str = Field(min_length=11, max_length=18)
    verify_code: str = Field(pattern=r"^[0-9]{4,8}$")


class TaskCreateRequest(BaseModel):
    source_file_id: str
    task_type: TaskType
    multiplier: int


class AttemptView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    attempt_number: int
    status: TaskStatus
    worker_id: str | None
    error_code: str | None
    retryable: bool
    created_at: datetime


class TaskView(BaseModel):
    id: str
    task_type: TaskType
    multiplier: int
    status: TaskStatus
    status_reason: str | None
    progress: int
    cost_points: int
    charged_points: int
    refunded_points: int
    source_file_id: str
    output_file_id: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    attempts: list[AttemptView] = Field(default_factory=list)


class MediaView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    mime_type: str
    media_kind: str
    size_bytes: int
    duration_seconds: float | None
    width: int | None
    height: int | None
    is_output: bool
    deleted_at: datetime | None
    created_at: datetime


class TicketCreateRequest(BaseModel):
    task_id: str | None = None
    subject: str = Field(min_length=3, max_length=180)
    content: str = Field(min_length=10, max_length=10000)


class CopyrightCreateRequest(BaseModel):
    email: EmailStr
    subject: str = Field(min_length=3, max_length=180)
    content: str = Field(min_length=20, max_length=10000)
    task_id: str | None = None


class TicketView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str | None
    kind: TicketKind
    status: TicketStatus
    email: str | None
    subject: str
    content: str
    admin_reply: str | None
    created_at: datetime
    updated_at: datetime


class WorkerHeartbeatRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=120)
    capabilities: list[TaskType]


class WorkerClaimRequest(BaseModel):
    worker_id: str


class WorkerProgressRequest(BaseModel):
    status: TaskStatus
    progress: int = Field(ge=0, le=99)


class WorkerProviderBindingRequest(BaseModel):
    provider: str = Field(min_length=2, max_length=80)
    provider_task_id: str = Field(min_length=4, max_length=180)


class WorkerFailureRequest(BaseModel):
    error_code: str = Field(min_length=1, max_length=100)
    error_detail: str = Field(default="", max_length=4000)
    retryable: bool = True


class AdminAdjustmentRequest(BaseModel):
    user_id: str
    points: int = Field(ge=-100000, le=100000)
    idempotency_key: str = Field(min_length=8, max_length=160)
    reason: str = Field(min_length=3, max_length=300)


class AdminRefundRequest(BaseModel):
    points: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=160)
    reason: str = Field(min_length=3, max_length=300)


class AdminTicketUpdateRequest(BaseModel):
    status: TicketStatus
    admin_reply: str = Field(default="", max_length=10000)
