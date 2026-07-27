"""Auth and user schemas for /api/v1."""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "daughter@example.com",
                    "password": "child-pass",
                }
            ]
        }
    )

    # Username key (historically called email). No format validation.
    email: str = Field(..., min_length=1, max_length=320, examples=["daughter@example.com"])
    password: str = Field(..., min_length=1, max_length=256, examples=["child-pass"])


class UserOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "email": "daughter@example.com",
                    "first_name": "Sam",
                    "last_name": "Smith",
                    "display_name": "Sam Smith",
                    "role": "child",
                    "parent_id": 2,
                    "is_active": True,
                    "points_balance": 42,
                }
            ]
        },
    )

    id: int
    email: str
    first_name: str
    last_name: str
    display_name: str
    role: str
    parent_id: int | None = None
    is_active: bool = True
    points_balance: int = 0


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "opaque-signed-token…",
                    "token_type": "bearer",
                    "expires_in": 1209600,
                    "user": {
                        "id": 1,
                        "email": "daughter@example.com",
                        "first_name": "Sam",
                        "last_name": "Smith",
                        "display_name": "Sam Smith",
                        "role": "child",
                        "parent_id": 2,
                        "is_active": True,
                        "points_balance": 42,
                    },
                }
            ]
        }
    )

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class AdminRegisterRequest(BaseModel):
    """Bootstrap registration via admin API key (typically a parent)."""

    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=256)
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    role: str = Field(default="parent", description="parent or child (child requires parent_id)")
    parent_id: int | None = None


class ChildCreateRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=256)
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)


class ChildUpdateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=1, max_length=320)
    password: str | None = Field(default=None, max_length=256)
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    is_active: bool | None = None


class ChildListResponse(BaseModel):
    children: list[UserOut]
