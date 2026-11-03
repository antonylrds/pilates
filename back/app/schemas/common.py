from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Phone = Annotated[str, Field(min_length=8, max_length=30)]
PhoneList = Annotated[list[Phone], Field(max_length=5)]
EmailList = Annotated[list[EmailStr], Field(max_length=5)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str
