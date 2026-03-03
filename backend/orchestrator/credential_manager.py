"""
Credential Manager — Per-user, per-agent encrypted credential storage.

Provides secure storage for external API keys and OAuth tokens that
agents need to access third-party services. Credentials are encrypted
at rest using Fernet symmetric encryption.

Mirrors the ToolPermissionManager pattern for consistency.
"""
import os
import time
import logging
from typing import Dict, List, Optional

from cryptography.fernet import Fernet

logger = logging.getLogger("CredentialManager")


class CredentialManager:
    """Manages per-user, per-agent encrypted credentials backed by SQLite.

    Structure (logical):
        {
            "<user_id>": {
                "<agent_id>": {
                    "CREDENTIAL_KEY": "decrypted_value",
                    ...
                }
            }
        }
    """

    def __init__(self, db=None, data_dir: str = None):
        if db is not None:
            self.db = db
        elif data_dir is not None:
            import sys
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
            from shared.database import Database
            db_path = os.path.join(data_dir, "chats.db")
            self.db = Database(db_path)
        else:
            raise ValueError("Either db or data_dir must be provided")

        self.data_dir = data_dir
        self._fernet = self._init_encryption()

    def _init_encryption(self) -> Fernet:
        """Initialize Fernet encryption using env var or auto-generated key file."""
        # Prefer env var
        env_key = os.getenv("CREDENTIAL_ENCRYPTION_KEY")
        if env_key:
            return Fernet(env_key.encode())

        # Auto-generate and persist key file
        key_dir = self.data_dir or os.path.join(os.path.dirname(__file__), '..', 'data')
        key_path = os.path.join(key_dir, ".credential_key")

        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, "wb") as f:
                f.write(key)
            logger.info("Generated new credential encryption key")

        return Fernet(key)

    def set_credential(self, user_id: str, agent_id: str, key: str, value: str):
        """Encrypt and store a credential."""
        encrypted = self._fernet.encrypt(value.encode()).decode()
        now = int(time.time() * 1000)
        self.db.execute(
            """INSERT OR REPLACE INTO user_credentials
               (user_id, agent_id, credential_key, encrypted_value, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, agent_id, key, encrypted, now, now)
        )
        logger.info(f"Credential set: user={user_id} agent={agent_id} key={key}")

    def get_credential(self, user_id: str, agent_id: str, key: str) -> Optional[str]:
        """Decrypt and return a single credential, or None if not found."""
        row = self.db.fetch_one(
            "SELECT encrypted_value FROM user_credentials WHERE user_id = ? AND agent_id = ? AND credential_key = ?",
            (user_id, agent_id, key)
        )
        if row is None:
            return None
        try:
            return self._fernet.decrypt(row['encrypted_value'].encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt credential: user={user_id} agent={agent_id} key={key}: {e}")
            return None

    def get_agent_credentials(self, user_id: str, agent_id: str) -> Dict[str, str]:
        """Decrypt and return all credentials for a user+agent combination.
        Internal keys (starting with '_') are excluded."""
        rows = self.db.fetch_all(
            "SELECT credential_key, encrypted_value FROM user_credentials WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        result = {}
        for row in rows:
            key = row['credential_key']
            if key.startswith('_'):
                continue  # Skip internal keys like _oauth_state
            try:
                result[key] = self._fernet.decrypt(
                    row['encrypted_value'].encode()
                ).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt credential {key}: {e}")
        return result

    def delete_credential(self, user_id: str, agent_id: str, key: str):
        """Remove a single credential."""
        self.db.execute(
            "DELETE FROM user_credentials WHERE user_id = ? AND agent_id = ? AND credential_key = ?",
            (user_id, agent_id, key)
        )
        logger.info(f"Credential deleted: user={user_id} agent={agent_id} key={key}")

    def list_credential_keys(self, user_id: str, agent_id: str) -> List[str]:
        """List stored credential keys (without values) for a user+agent."""
        rows = self.db.fetch_all(
            "SELECT credential_key FROM user_credentials WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        return [row['credential_key'] for row in rows]

    def set_bulk_credentials(self, user_id: str, agent_id: str, credentials: Dict[str, str]):
        """Set multiple credentials at once."""
        for key, value in credentials.items():
            self.set_credential(user_id, agent_id, key, value)

    def remove_agent_credentials(self, user_id: str, agent_id: str):
        """Remove all credentials for a specific agent under a user."""
        self.db.execute(
            "DELETE FROM user_credentials WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        logger.info(f"All credentials removed: user={user_id} agent={agent_id}")
