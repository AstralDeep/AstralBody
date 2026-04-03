"""
Credential Manager — Per-user, per-agent encrypted credential storage.

Supports two encryption modes:
- **Fernet** (legacy/OAuth): Symmetric encryption where the orchestrator holds the key.
  Used for credentials the orchestrator itself needs to read (e.g., OAuth flows).
- **ECIES** (E2E): Asymmetric encryption using the agent's EC P-256 public key.
  The orchestrator encrypts but cannot decrypt — only the target agent can.

Mirrors the ToolPermissionManager pattern for consistency.
"""
import os
import time
import logging
from typing import Dict, List, Optional

from cryptography.fernet import Fernet

from shared.crypto import (
    encrypt_for_agent, ec_public_key_from_jwk, is_e2e_encrypted,
)

logger = logging.getLogger("CredentialManager")


class CredentialManager:
    """Manages per-user, per-agent encrypted credentials backed by PostgreSQL.

    Structure (logical):
        {
            "<user_id>": {
                "<agent_id>": {
                    "CREDENTIAL_KEY": "encrypted_value",
                    ...
                }
            }
        }
    """

    def __init__(self, db=None, data_dir: str = None, database_url: str = None):
        if db is not None:
            self.db = db
        elif data_dir is not None or database_url is not None:
            import sys
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
            from shared.database import Database
            self.db = Database(database_url)
        else:
            raise ValueError("Either db, data_dir, or database_url must be provided")

        self.data_dir = data_dir
        self._fernet = self._init_encryption()

        # Agent public keys for ECIES encryption (agent_id -> JWK dict)
        self._agent_public_keys: Dict[str, dict] = {}

    def _init_encryption(self) -> Fernet:
        """Initialize Fernet encryption using env var or auto-generated key file."""
        env_key = os.getenv("CREDENTIAL_ENCRYPTION_KEY")
        if env_key:
            return Fernet(env_key.encode())

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

    # ------------------------------------------------------------------
    # Agent Public Key Registry (for ECIES)
    # ------------------------------------------------------------------

    def register_agent_public_key(self, agent_id: str, jwk: dict):
        """Store an agent's ECIES public key (JWK) for E2E credential encryption."""
        self._agent_public_keys[agent_id] = jwk
        logger.info(f"Registered ECIES public key for agent '{agent_id}'")

    def has_agent_public_key(self, agent_id: str) -> bool:
        """Check if an agent has a registered ECIES public key."""
        return agent_id in self._agent_public_keys

    # ------------------------------------------------------------------
    # Credential Storage
    # ------------------------------------------------------------------

    def set_credential(self, user_id: str, agent_id: str, key: str, value: str, e2e: bool = True):
        """Encrypt and store a credential.

        Args:
            user_id: The user who owns the credential.
            agent_id: The agent this credential is for.
            key: Credential key name (e.g., "NOCODB_API_TOKEN").
            value: Plaintext credential value.
            e2e: If True and the agent has a registered public key, use ECIES.
                 If False, always use Fernet (for OAuth credentials the orchestrator needs).
        """
        if e2e and agent_id in self._agent_public_keys:
            agent_pub = ec_public_key_from_jwk(self._agent_public_keys[agent_id])
            encrypted = encrypt_for_agent(value, agent_pub)
        else:
            encrypted = self._fernet.encrypt(value.encode()).decode()

        now = int(time.time() * 1000)
        self.db.execute(
            """INSERT INTO user_credentials
               (user_id, agent_id, credential_key, encrypted_value, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (user_id, agent_id, credential_key)
               DO UPDATE SET encrypted_value = EXCLUDED.encrypted_value, updated_at = EXCLUDED.updated_at""",
            (user_id, agent_id, key, encrypted, now, now)
        )
        mode = "E2E/ECIES" if encrypted.startswith("e2e:") else "Fernet"
        logger.info(f"Credential set ({mode}): user={user_id} agent={agent_id} key={key}")

    def get_credential(self, user_id: str, agent_id: str, key: str) -> Optional[str]:
        """Decrypt and return a single Fernet-encrypted credential, or None.

        Only works for Fernet-encrypted values (OAuth credentials).
        E2E-encrypted values cannot be decrypted by the orchestrator.
        """
        row = self.db.fetch_one(
            "SELECT encrypted_value FROM user_credentials WHERE user_id = ? AND agent_id = ? AND credential_key = ?",
            (user_id, agent_id, key)
        )
        if row is None:
            return None
        value = row['encrypted_value']
        if is_e2e_encrypted(value):
            logger.error(f"Cannot decrypt E2E credential on orchestrator: key={key}")
            return None
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt credential: user={user_id} agent={agent_id} key={key}: {e}")
            return None

    def get_agent_credentials(self, user_id: str, agent_id: str) -> Dict[str, str]:
        """Decrypt and return all Fernet-encrypted credentials for a user+agent.

        Only returns Fernet-encrypted values (OAuth credentials the orchestrator needs).
        Internal keys (starting with '_') are excluded.
        E2E-encrypted values are skipped.
        """
        rows = self.db.fetch_all(
            "SELECT credential_key, encrypted_value FROM user_credentials WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        result = {}
        for row in rows:
            key = row['credential_key']
            if key.startswith('_'):
                continue
            value = row['encrypted_value']
            if is_e2e_encrypted(value):
                continue  # Skip E2E — orchestrator can't decrypt these
            try:
                result[key] = self._fernet.decrypt(value.encode()).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt credential {key}: {e}")
        return result

    def get_agent_credentials_encrypted(self, user_id: str, agent_id: str) -> Dict[str, str]:
        """Return raw encrypted credential values for passing to agents.

        Returns ciphertext as-is (both Fernet and ECIES blobs).
        The agent will decrypt E2E values; Fernet values pass through for
        backward compatibility during migration.
        Internal keys (starting with '_') are excluded.
        """
        rows = self.db.fetch_all(
            "SELECT credential_key, encrypted_value FROM user_credentials WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        result = {}
        for row in rows:
            key = row['credential_key']
            if key.startswith('_'):
                continue
            result[key] = row['encrypted_value']
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

    def set_bulk_credentials(self, user_id: str, agent_id: str, credentials: Dict[str, str], e2e: bool = True):
        """Set multiple credentials at once."""
        for key, value in credentials.items():
            self.set_credential(user_id, agent_id, key, value, e2e=e2e)

    def remove_agent_credentials(self, user_id: str, agent_id: str):
        """Remove all credentials for a specific agent under a user."""
        self.db.execute(
            "DELETE FROM user_credentials WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        logger.info(f"All credentials removed: user={user_id} agent={agent_id}")

    # ------------------------------------------------------------------
    # Migration: Re-encrypt Fernet credentials to ECIES
    # ------------------------------------------------------------------

    def migrate_to_e2e(self, agent_id: str) -> int:
        """Re-encrypt all Fernet credentials for an agent using ECIES.

        Requires the agent's public key to be registered.
        Returns the number of credentials migrated.
        """
        if agent_id not in self._agent_public_keys:
            logger.error(f"Cannot migrate: no public key for agent '{agent_id}'")
            return 0

        agent_pub = ec_public_key_from_jwk(self._agent_public_keys[agent_id])
        rows = self.db.fetch_all(
            "SELECT user_id, credential_key, encrypted_value FROM user_credentials WHERE agent_id = ?",
            (agent_id,)
        )

        migrated = 0
        for row in rows:
            key = row['credential_key']
            value = row['encrypted_value']

            if key.startswith('_') or is_e2e_encrypted(value):
                continue  # Skip internal keys and already-migrated values

            try:
                plaintext = self._fernet.decrypt(value.encode()).decode()
                encrypted = encrypt_for_agent(plaintext, agent_pub)
                now = int(time.time() * 1000)
                self.db.execute(
                    """UPDATE user_credentials
                       SET encrypted_value = ?, updated_at = ?
                       WHERE user_id = ? AND agent_id = ? AND credential_key = ?""",
                    (encrypted, now, row['user_id'], agent_id, key)
                )
                migrated += 1
            except Exception as e:
                logger.error(f"Migration failed for {key}: {e}")

        logger.info(f"Migrated {migrated} credentials to E2E for agent '{agent_id}'")
        return migrated
