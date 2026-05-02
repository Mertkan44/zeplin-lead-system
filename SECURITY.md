# Security Notes

The local `.env` file is ignored, but a secret was committed in early history. Rotate the Groq key before treating this repository as safe.

Recommended cleanup:

1. Rotate the Groq API key in the Groq dashboard.
2. Update local `.env` with the new value.
3. Purge `.env` from Git history with a history rewrite tool before sharing the repository.
4. Force-push only after every collaborator is aware of the rewrite.

Do not commit raw lead exports containing private phone numbers or addresses to a public repository.
