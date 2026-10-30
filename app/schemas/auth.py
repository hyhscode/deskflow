from pydantic import BaseModel

class LoginRequest(BaseModel):
    username:str
    password:str

class TokenOut(BaseModel):
    access_token:str
    token_tyre:str = "bearer"
    expires_in = int #有效期

class MeOut(BaseModel):
    id:int
    username:str
    real_name:str | None
    roles: list[str]
    permissions:list[str] = []