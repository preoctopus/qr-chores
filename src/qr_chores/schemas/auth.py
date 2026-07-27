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
                    "display_name": "Daughter",
                    "role": "child",
                    "points_balance": 42,
                }
            ]
        },
    )

    id: int
    email: str
    display_name: str
    role: str
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
                        "display_name": "Daughter",
                        "role": "child",
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
