import os
from datetime import timedelta
from dotenv import load_dotenv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

private_path = BASE_DIR / os.environ.get("JWT_PRIVATE_KEY_PATH", "keys/private_key.pem")
public_path = BASE_DIR / os.environ.get("JWT_PUBLIC_KEY_PATH", "keys/public_key.pem")

class Config:
  JWT_ALGORITHM = "RS256"

  JWT_PRIVATE_KEY = open(private_path).read()

  JWT_PUBLIC_KEY = open(public_path).read()

  JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=3)
