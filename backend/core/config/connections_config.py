"""Saved-connection credential encryption settings."""

import os


# Fernet key encrypting saved connections' credentials at rest (common/security/crypto.py).
# Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Local dev reads it from backend/.env; in a real deployment it is resolved from a secrets
# manager instead, the same way DATABASE_URL is. Empty by default on purpose - the app
# boots without it and only fails when a saved connection is actually used.
CONNECTION_ENCRYPTION_KEY = os.getenv("CONNECTION_ENCRYPTION_KEY", "")
