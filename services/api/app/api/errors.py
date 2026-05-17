from pydantic import BaseModel


class APIErrorBody(BaseModel):
    detail: str
    code: str | None = None
