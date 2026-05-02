import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def groq_client() -> Groq:
    load_env()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Copy .env.example to .env and add the key.")
    return Groq(api_key=api_key)
