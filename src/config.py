import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def groq_client() -> Groq:
    load_env()
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Copy .env.example to .env and add the key.")
    return Groq(api_key=api_key)


def env(name: str, default: str | None = None) -> str | None:
    load_env()
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


def required_env(name: str) -> str:
    value = env(name)
    if not value:
        raise RuntimeError(f"{name} is missing. Copy .env.example to .env and add the value.")
    return value
