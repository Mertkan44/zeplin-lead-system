import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_FILES = {".env", ".env.local", ".env.production", ".env.development"}
SECRET_PATTERNS = [
    ("Groq API key", re.compile(r"gsk_[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("Generic token assignment", re.compile(r"(?i)(api[_-]?key|secret|token)\s*=\s*['\"]?[A-Za-z0-9_./+=:-]{24,}")),
]
SKIP_DIRS = {".git", "venv", "node_modules", "__pycache__"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".pdf"}


def git_candidate_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return set(result.stdout.splitlines())


def iter_text_files(tracked: set[str]):
    for rel_name in sorted(tracked):
        path = ROOT / rel_name
        rel = Path(rel_name)
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    findings = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(label)
    return findings


def main() -> int:
    tracked = git_candidate_files()
    problems: list[str] = []

    for filename in BLOCKED_FILES:
        if filename in tracked:
            problems.append(f"tracked secret file: {filename}")

    for path in iter_text_files(tracked):
        rel = path.relative_to(ROOT).as_posix()
        if rel in {".env.example", "SECURITY.md", "scripts/security_check.py"}:
            continue
        findings = scan_file(path)
        for finding in findings:
            problems.append(f"{finding}: {rel}")

    if problems:
        print("Security check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("Security check passed: no tracked env files or obvious API keys found in the working tree.")
    if os.getenv("CI"):
        print("Reminder: rotate any key that was ever committed before deploying.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
