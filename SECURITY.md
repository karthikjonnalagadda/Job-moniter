# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability, please **do not open a public issue**.
Instead, report it privately via GitHub's
[private vulnerability reporting](https://github.com/karthikjonnalagadda/Job-moniter/security/advisories/new)
(Security → Report a vulnerability). We aim to acknowledge reports within a few
business days and will coordinate a fix and disclosure timeline with you.

## Secret handling

This project treats all credentials as environment-provided secrets. **No secret
is ever committed to the repository.**

- Configuration is loaded from environment variables (prefix `JOBAGENT_`) and
  validated at startup in `app/config/settings.py`.
- `.env` is git-ignored; only `.env.example` (placeholders) is committed.
- Sensitive fields (Mongo URI, SMTP password) are handled as secrets and are
  **never logged**.
- In production, secrets are injected as encrypted environment variables:
  - **Render:** `sync: false` env vars set in the dashboard (see `render.yaml`).
  - **GitHub Actions:** encrypted repository secrets
    (`JOBAGENT_MONGO_URI`, `JOBAGENT_SMTP_USERNAME`, `JOBAGENT_SMTP_PASSWORD`,
    `JOBAGENT_SMTP_TO_ADDRESS`).

## What to do if a secret is exposed

If a credential is ever committed or leaked:

1. **Rotate it immediately** at the source (MongoDB Atlas database user, Gmail
   App Password, etc.).
2. Remove it from history and force-push, or rotate and move on — rotation is
   the reliable remediation.
3. Confirm the new value is only present in your local `.env` / deployment
   secrets.

## Supported versions

The latest release on `main` receives security fixes. Older tags are not
maintained.
