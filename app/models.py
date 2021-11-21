from bson import ObjectId
from pydantic import BaseModel, Field, AnyUrl, SecretStr
from typing import List, Dict, Optional
from datetime import date
import time


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class URLModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    long_url: AnyUrl = Field(...)
    short_url: str = Field(...)
    hits: int = Field(...)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "long_url": "https://www.google.com/search?q=ejwjd&oq=ejwjd&aqs=chrome..69i57.2029j0j1&sourceid=chrome&ie=UTF-8",
                "short_url": "http://example.com/abcdef",
            }
        }


class User(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    email: str = Field(...)
    username: str = Field(...)
    password: str = Field(...)
    urls: List[Optional[Dict[str, List[str]]]] = Field(...)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "email": "xyz@example.com",
                "username": "example",
                "password": "pass12345",
                "urls": [
                    {
                        "url": "https://example.com/abcdefghi/sjwjsjsjs/wjwjsjsj",
                        "aliases": ["cdefgh", "ghefgh"],
                    }
                ],
            }
        }
