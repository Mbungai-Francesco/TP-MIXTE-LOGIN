from typing import TypedDict
from typing_extensions import NotRequired

class UserProfile(TypedDict):
    id: str
    email: str
    password: NotRequired[str]  # Marked as NotRequired since we remove it
    role: str
    name: str
    last_active: int