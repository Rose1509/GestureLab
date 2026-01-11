from pydantic import BaseModel, Field, constr, EmailStr, validator

class UserCreate(BaseModel):
    email: EmailStr
    username: constr(strip_whitespace=True, min_length=3, max_length=50)
    password: constr(min_length=6, max_length=72)        
    confirm_password: constr(min_length=6, max_length=72)


    @validator("confirm_password")
    def passwords_match(cls, v, values):
        if "password" in values and v != values["password"]:
            raise ValueError("Passwords do not match")
        return v
