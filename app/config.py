import os
from dotenv import load_dotenv

load_dotenv()

HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY") or None
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or None
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
ACORN_USER = os.getenv("ACORN_USER", "demo")
DATA_DIR = os.getenv("ACORN_DATA_DIR", "data")
