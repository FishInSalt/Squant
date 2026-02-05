"""AES-GCM encryption utilities for secure credential storage."""

from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from squant.config import get_settings


class CryptoError(Exception):
    """Base exception for crypto operations."""

    pass


class EncryptionError(CryptoError):
    """Error during encryption."""

    pass


class DecryptionError(CryptoError):
    """Error during decryption."""

    pass


class CryptoManager:
    """AES-256-GCM encryption manager for secure credential storage.

    Uses AES-256-GCM (Galois/Counter Mode) which provides:
    - Authenticated encryption (confidentiality + integrity)
    - 256-bit key for strong security
    - Random nonce for each encryption operation
    """

    NONCE_SIZE = 12  # 96 bits, recommended for GCM

    def __init__(self, key: bytes) -> None:
        """Initialize CryptoManager with a 32-byte key.

        Args:
            key: 32-byte (256-bit) encryption key.

        Raises:
            ValueError: If key is not 32 bytes.
        """
        if len(key) != 32:
            raise ValueError("Encryption key must be 32 bytes (256 bits)")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str, nonce: bytes | None = None) -> tuple[bytes, bytes]:
        """Encrypt plaintext string using AES-256-GCM.

        Args:
            plaintext: Text to encrypt.
            nonce: Optional nonce to use. If not provided, generates a random one.
                   WARNING: Never reuse the same nonce with the same key for
                   different plaintexts - this breaks GCM security.

        Returns:
            Tuple of (ciphertext, nonce).

        Raises:
            EncryptionError: If encryption fails.
        """
        if not plaintext:
            raise EncryptionError("Cannot encrypt empty string")

        try:
            if nonce is None:
                nonce = os.urandom(self.NONCE_SIZE)
            elif len(nonce) != self.NONCE_SIZE:
                raise EncryptionError(f"Nonce must be {self.NONCE_SIZE} bytes")

            ciphertext = self._aesgcm.encrypt(
                nonce, plaintext.encode("utf-8"), associated_data=None
            )
            return ciphertext, nonce
        except EncryptionError:
            raise
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(self, ciphertext: bytes, nonce: bytes) -> str:
        """Decrypt ciphertext using AES-256-GCM.

        Args:
            ciphertext: Encrypted data.
            nonce: Nonce used during encryption.

        Returns:
            Decrypted plaintext string.

        Raises:
            DecryptionError: If decryption fails (invalid key, tampered data, etc.).
        """
        if not ciphertext or not nonce:
            raise DecryptionError("Cannot decrypt: missing ciphertext or nonce")

        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            return plaintext.decode("utf-8")
        except Exception:
            # Security: Use generic message to avoid leaking implementation details
            raise DecryptionError("Decryption failed: data may be corrupted or key mismatch")

    def derive_nonce(self, base_nonce: bytes, index: int) -> bytes:
        """Derive a unique nonce from base nonce and index.

        Uses XOR on the last bytes to create unique nonces for multi-field
        encryption while sharing a single stored nonce.

        Args:
            base_nonce: The base nonce (12 bytes).
            index: Derivation index (0-255 for single byte, supports larger).

        Returns:
            Derived nonce of same size.

        Raises:
            ValueError: If base_nonce is wrong size or index is negative.
        """
        if len(base_nonce) != self.NONCE_SIZE:
            raise ValueError(f"Base nonce must be {self.NONCE_SIZE} bytes")
        if index < 0:
            raise ValueError("Index must be non-negative")

        # XOR index into the last bytes of the nonce
        nonce = bytearray(base_nonce)
        # Use up to 4 bytes for index to support larger values
        for i in range(min(4, self.NONCE_SIZE)):
            nonce[-(i + 1)] ^= (index >> (8 * i)) & 0xFF

        return bytes(nonce)

    def encrypt_with_derived_nonce(self, plaintext: str, base_nonce: bytes, index: int) -> bytes:
        """Encrypt using a derived nonce.

        Useful for encrypting multiple fields with a single stored nonce.

        Args:
            plaintext: Text to encrypt.
            base_nonce: Base nonce for derivation.
            index: Derivation index (use different index for each field).

        Returns:
            Ciphertext only (nonce is derivable from base_nonce + index).
        """
        derived_nonce = self.derive_nonce(base_nonce, index)
        ciphertext, _ = self.encrypt(plaintext, nonce=derived_nonce)
        return ciphertext

    def decrypt_with_derived_nonce(self, ciphertext: bytes, base_nonce: bytes, index: int) -> str:
        """Decrypt using a derived nonce.

        Args:
            ciphertext: Encrypted data.
            base_nonce: Base nonce for derivation.
            index: Derivation index used during encryption.

        Returns:
            Decrypted plaintext string.
        """
        derived_nonce = self.derive_nonce(base_nonce, index)
        return self.decrypt(ciphertext, derived_nonce)

    def encrypt_to_base64(self, plaintext: str) -> tuple[str, str]:
        """Encrypt and return base64-encoded ciphertext and nonce.

        Useful for JSON serialization.

        Args:
            plaintext: Text to encrypt.

        Returns:
            Tuple of (base64_ciphertext, base64_nonce).
        """
        ciphertext, nonce = self.encrypt(plaintext)
        return (
            base64.b64encode(ciphertext).decode("ascii"),
            base64.b64encode(nonce).decode("ascii"),
        )

    def decrypt_from_base64(self, b64_ciphertext: str, b64_nonce: str) -> str:
        """Decrypt base64-encoded ciphertext.

        Args:
            b64_ciphertext: Base64-encoded ciphertext.
            b64_nonce: Base64-encoded nonce.

        Returns:
            Decrypted plaintext string.
        """
        ciphertext = base64.b64decode(b64_ciphertext)
        nonce = base64.b64decode(b64_nonce)
        return self.decrypt(ciphertext, nonce)


@lru_cache
def get_crypto_manager() -> CryptoManager:
    """Get cached CryptoManager instance using settings.encryption_key.

    The encryption key should be either:
    - A 32-character ASCII string (will be encoded as UTF-8)
    - A 44-character base64-encoded 32-byte key

    Returns:
        CryptoManager initialized with the application's encryption key.

    Raises:
        ValueError: If encryption_key is not configured or invalid format.
    """
    settings = get_settings()
    key = settings.encryption_key.get_secret_value()

    # Support both raw 32-char ASCII and base64-encoded keys
    if len(key) == 44 and key.endswith("="):
        # Likely base64-encoded 32-byte key
        try:
            key_bytes = base64.b64decode(key)
            if len(key_bytes) != 32:
                raise ValueError(f"Base64-decoded key must be 32 bytes, got {len(key_bytes)}")
        except Exception as e:
            raise ValueError(f"Invalid base64 encryption key: {e}") from e
    elif len(key) == 32:
        # 32-character ASCII key
        key_bytes = key.encode("ascii")
    else:
        raise ValueError(
            f"ENCRYPTION_KEY must be 32 ASCII characters or 44-char base64 "
            f"(32 bytes encoded), got {len(key)} characters. "
            f'Generate with: python -c "import secrets; print(secrets.token_urlsafe(32)[:32])"'
        )

    return CryptoManager(key_bytes)


def encrypt_string(plaintext: str) -> str:
    """Encrypt a string using the application's encryption key.

    Args:
        plaintext: The string to encrypt.

    Returns:
        Base64-encoded encrypted string (nonce + ciphertext).

    Raises:
        EncryptionError: If encryption fails.
    """
    crypto_manager = get_crypto_manager()
    # Generate random nonce
    nonce = os.urandom(CryptoManager.NONCE_SIZE)
    # Encrypt
    ciphertext, nonce_used = crypto_manager.encrypt(plaintext, nonce)
    # Combine nonce and ciphertext, then base64 encode
    combined = nonce_used + ciphertext
    return base64.b64encode(combined).decode("ascii")


def decrypt_string(encrypted: str) -> str:
    """Decrypt a string encrypted with encrypt_string.

    Args:
        encrypted: Base64-encoded encrypted string (nonce + ciphertext).

    Returns:
        Decrypted plaintext string.

    Raises:
        DecryptionError: If decryption fails.
    """
    crypto_manager = get_crypto_manager()
    # Decode from base64
    combined = base64.b64decode(encrypted)
    # Split nonce and ciphertext
    nonce = combined[: CryptoManager.NONCE_SIZE]
    ciphertext = combined[CryptoManager.NONCE_SIZE :]
    # Decrypt
    return crypto_manager.decrypt(ciphertext, nonce)
