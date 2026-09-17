from pydantic import BaseModel, EmailStr, Field, model_validator

from .security import validate_password


class EmailInput(BaseModel):
    email: EmailStr

    @model_validator(mode='after')
    def normalize(self):
        self.email = str(self.email).lower()
        return self


class PasswordInput(BaseModel):
    password: str = Field(max_length=72)
    password_confirmation: str = Field(max_length=72)

    @model_validator(mode='after')
    def policy(self):
        validate_password(self.password)
        if self.password != self.password_confirmation:
            raise ValueError('Passwords do not match')
        return self


class Registration(EmailInput, PasswordInput):
    display_name: str = Field(default='', max_length=100)
    remember: bool = False


class Login(EmailInput):
    password: str = Field(max_length=1000)
    remember: bool = False


class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class Reset(PasswordInput, TokenInput):
    pass
