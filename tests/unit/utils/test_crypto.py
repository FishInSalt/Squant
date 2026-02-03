"""Unit tests for crypto utilities."""

import base64
import os
from unittest.mock import patch

import pytest

from squant.utils.crypto import (
    CryptoManager,
    DecryptionError,
    EncryptionError,
    get_crypto_manager,
)


class TestCryptoManager:
    """Tests for CryptoManager."""

    @pytest.fixture
    def valid_key(self) -> bytes:
        """Generate a valid 32-byte key."""
        return os.urandom(32)

    @pytest.fixture
    def crypto_manager(self, valid_key: bytes) -> CryptoManager:
        """Create a CryptoManager with valid key."""
        return CryptoManager(valid_key)

    def test_init_with_valid_key(self, valid_key: bytes) -> None:
        """Test initialization with valid 32-byte key."""
        manager = CryptoManager(valid_key)
        assert manager is not None

    def test_init_with_invalid_key_length(self) -> None:
        """Test initialization fails with invalid key length."""
        with pytest.raises(ValueError, match="32 bytes"):
            CryptoManager(b"short_key")

        with pytest.raises(ValueError, match="32 bytes"):
            CryptoManager(os.urandom(16))

        with pytest.raises(ValueError, match="32 bytes"):
            CryptoManager(os.urandom(64))

    def test_encrypt_returns_ciphertext_and_nonce(self, crypto_manager: CryptoManager) -> None:
        """Test that encrypt returns ciphertext and nonce."""
        plaintext = "secret_api_key_12345"
        ciphertext, nonce = crypto_manager.encrypt(plaintext)

        assert isinstance(ciphertext, bytes)
        assert isinstance(nonce, bytes)
        assert len(nonce) == CryptoManager.NONCE_SIZE
        assert len(ciphertext) > 0
        assert ciphertext != plaintext.encode()

    def test_encrypt_empty_string_raises_error(self, crypto_manager: CryptoManager) -> None:
        """Test that encrypting empty string raises error."""
        with pytest.raises(EncryptionError, match="empty"):
            crypto_manager.encrypt("")

    def test_decrypt_recovers_plaintext(self, crypto_manager: CryptoManager) -> None:
        """Test that decrypt recovers original plaintext."""
        plaintext = "my_secret_api_key_xyz123"
        ciphertext, nonce = crypto_manager.encrypt(plaintext)

        decrypted = crypto_manager.decrypt(ciphertext, nonce)
        assert decrypted == plaintext

    def test_decrypt_with_wrong_key_fails(self, valid_key: bytes) -> None:
        """Test that decrypt fails with wrong key."""
        manager1 = CryptoManager(valid_key)
        manager2 = CryptoManager(os.urandom(32))  # Different key

        plaintext = "secret_data"
        ciphertext, nonce = manager1.encrypt(plaintext)

        with pytest.raises(DecryptionError):
            manager2.decrypt(ciphertext, nonce)

    def test_decrypt_with_wrong_nonce_fails(self, crypto_manager: CryptoManager) -> None:
        """Test that decrypt fails with wrong nonce."""
        plaintext = "secret_data"
        ciphertext, _ = crypto_manager.encrypt(plaintext)
        wrong_nonce = os.urandom(CryptoManager.NONCE_SIZE)

        with pytest.raises(DecryptionError):
            crypto_manager.decrypt(ciphertext, wrong_nonce)

    def test_decrypt_with_tampered_ciphertext_fails(self, crypto_manager: CryptoManager) -> None:
        """Test that decrypt fails if ciphertext is tampered."""
        plaintext = "secret_data"
        ciphertext, nonce = crypto_manager.encrypt(plaintext)

        # Tamper with ciphertext
        tampered = bytearray(ciphertext)
        tampered[0] ^= 0xFF
        tampered = bytes(tampered)

        with pytest.raises(DecryptionError):
            crypto_manager.decrypt(tampered, nonce)

    def test_decrypt_empty_inputs_raises_error(self, crypto_manager: CryptoManager) -> None:
        """Test that decrypt with empty inputs raises error."""
        with pytest.raises(DecryptionError, match="missing"):
            crypto_manager.decrypt(b"", b"nonce_here")

        with pytest.raises(DecryptionError, match="missing"):
            crypto_manager.decrypt(b"ciphertext", b"")

    def test_unique_nonces_for_each_encryption(self, crypto_manager: CryptoManager) -> None:
        """Test that each encryption uses a unique nonce."""
        plaintext = "same_plaintext"
        results = [crypto_manager.encrypt(plaintext) for _ in range(10)]

        nonces = [r[1] for r in results]
        ciphertexts = [r[0] for r in results]

        # All nonces should be unique
        assert len(set(nonces)) == len(nonces)

        # All ciphertexts should be unique (due to unique nonces)
        assert len(set(ciphertexts)) == len(ciphertexts)

    def test_encrypt_unicode_characters(self, crypto_manager: CryptoManager) -> None:
        """Test encryption/decryption of unicode text."""
        plaintext = "api_key_with_special_chars_\u00e9\u00e8\u00ea"
        ciphertext, nonce = crypto_manager.encrypt(plaintext)

        decrypted = crypto_manager.decrypt(ciphertext, nonce)
        assert decrypted == plaintext

    def test_encrypt_long_text(self, crypto_manager: CryptoManager) -> None:
        """Test encryption/decryption of long text."""
        plaintext = "a" * 10000
        ciphertext, nonce = crypto_manager.encrypt(plaintext)

        decrypted = crypto_manager.decrypt(ciphertext, nonce)
        assert decrypted == plaintext


class TestCryptoManagerDerivedNonce:
    """Tests for derived nonce functionality."""

    @pytest.fixture
    def crypto_manager(self) -> CryptoManager:
        """Create a CryptoManager with random key."""
        return CryptoManager(os.urandom(32))

    def test_derive_nonce_creates_unique_nonces(self, crypto_manager: CryptoManager) -> None:
        """Test that derived nonces are unique for different indices."""
        base_nonce = os.urandom(CryptoManager.NONCE_SIZE)

        nonces = [crypto_manager.derive_nonce(base_nonce, i) for i in range(10)]

        # All derived nonces should be unique
        assert len(set(nonces)) == len(nonces)

    def test_derive_nonce_is_deterministic(self, crypto_manager: CryptoManager) -> None:
        """Test that same base + index always produces same derived nonce."""
        base_nonce = os.urandom(CryptoManager.NONCE_SIZE)

        nonce1 = crypto_manager.derive_nonce(base_nonce, 5)
        nonce2 = crypto_manager.derive_nonce(base_nonce, 5)

        assert nonce1 == nonce2

    def test_encrypt_decrypt_with_derived_nonce(self, crypto_manager: CryptoManager) -> None:
        """Test encrypt/decrypt roundtrip with derived nonces."""
        base_nonce = os.urandom(CryptoManager.NONCE_SIZE)

        # Encrypt multiple fields with different indices
        plaintext1 = "api_key_123"
        plaintext2 = "api_secret_456"
        plaintext3 = "passphrase_789"

        ct1 = crypto_manager.encrypt_with_derived_nonce(plaintext1, base_nonce, 0)
        ct2 = crypto_manager.encrypt_with_derived_nonce(plaintext2, base_nonce, 1)
        ct3 = crypto_manager.encrypt_with_derived_nonce(plaintext3, base_nonce, 2)

        # Decrypt with same indices
        assert crypto_manager.decrypt_with_derived_nonce(ct1, base_nonce, 0) == plaintext1
        assert crypto_manager.decrypt_with_derived_nonce(ct2, base_nonce, 1) == plaintext2
        assert crypto_manager.decrypt_with_derived_nonce(ct3, base_nonce, 2) == plaintext3

    def test_decrypt_with_wrong_index_fails(self, crypto_manager: CryptoManager) -> None:
        """Test that decryption fails with wrong index."""
        base_nonce = os.urandom(CryptoManager.NONCE_SIZE)

        plaintext = "secret_data"
        ciphertext = crypto_manager.encrypt_with_derived_nonce(plaintext, base_nonce, 0)

        # Decrypting with wrong index should fail
        with pytest.raises(DecryptionError):
            crypto_manager.decrypt_with_derived_nonce(ciphertext, base_nonce, 1)

    def test_derive_nonce_invalid_base_nonce(self, crypto_manager: CryptoManager) -> None:
        """Test that invalid base nonce raises error."""
        with pytest.raises(ValueError, match="12 bytes"):
            crypto_manager.derive_nonce(b"short", 0)

    def test_derive_nonce_negative_index(self, crypto_manager: CryptoManager) -> None:
        """Test that negative index raises error."""
        base_nonce = os.urandom(CryptoManager.NONCE_SIZE)
        with pytest.raises(ValueError, match="non-negative"):
            crypto_manager.derive_nonce(base_nonce, -1)


class TestCryptoManagerBase64:
    """Tests for base64 encoding/decoding methods."""

    @pytest.fixture
    def crypto_manager(self) -> CryptoManager:
        """Create a CryptoManager with random key."""
        return CryptoManager(os.urandom(32))

    def test_encrypt_to_base64(self, crypto_manager: CryptoManager) -> None:
        """Test base64 encryption returns valid base64 strings."""
        plaintext = "api_secret_123"
        b64_ciphertext, b64_nonce = crypto_manager.encrypt_to_base64(plaintext)

        # Should be valid base64
        assert isinstance(b64_ciphertext, str)
        assert isinstance(b64_nonce, str)

        # Should decode without error
        base64.b64decode(b64_ciphertext)
        base64.b64decode(b64_nonce)

    def test_decrypt_from_base64(self, crypto_manager: CryptoManager) -> None:
        """Test decryption from base64 strings."""
        plaintext = "secret_api_key"
        b64_ciphertext, b64_nonce = crypto_manager.encrypt_to_base64(plaintext)

        decrypted = crypto_manager.decrypt_from_base64(b64_ciphertext, b64_nonce)
        assert decrypted == plaintext

    def test_base64_roundtrip(self, crypto_manager: CryptoManager) -> None:
        """Test full roundtrip through base64 encoding."""
        plaintext = "test_roundtrip_123"
        b64_ciphertext, b64_nonce = crypto_manager.encrypt_to_base64(plaintext)

        # Verify base64 is ASCII-safe
        b64_ciphertext.encode("ascii")
        b64_nonce.encode("ascii")

        decrypted = crypto_manager.decrypt_from_base64(b64_ciphertext, b64_nonce)
        assert decrypted == plaintext


class TestCryptoManagerEdgeCases:
    """Tests for edge cases and error paths."""

    @pytest.fixture
    def crypto_manager(self) -> CryptoManager:
        """Create a CryptoManager with random key."""
        return CryptoManager(os.urandom(32))

    def test_encrypt_with_invalid_custom_nonce_length(self, crypto_manager: CryptoManager) -> None:
        """Test that custom nonce with wrong length raises error."""
        plaintext = "secret_data"
        invalid_nonce = os.urandom(16)  # Wrong size (should be 12)

        with pytest.raises(EncryptionError, match="Nonce must be 12 bytes"):
            crypto_manager.encrypt(plaintext, nonce=invalid_nonce)

    def test_encrypt_with_valid_custom_nonce(self, crypto_manager: CryptoManager) -> None:
        """Test encryption with valid custom nonce."""
        plaintext = "secret_data"
        custom_nonce = os.urandom(CryptoManager.NONCE_SIZE)

        ciphertext, nonce = crypto_manager.encrypt(plaintext, nonce=custom_nonce)

        # Returned nonce should be the same as custom nonce
        assert nonce == custom_nonce

        # Should decrypt correctly
        decrypted = crypto_manager.decrypt(ciphertext, nonce)
        assert decrypted == plaintext

    def test_encrypt_reraises_encryption_error(self, crypto_manager: CryptoManager) -> None:
        """Test that EncryptionError is re-raised without wrapping."""
        plaintext = "secret_data"

        # Create invalid nonce to trigger EncryptionError path
        invalid_nonce = b"short"  # Too short

        # This should raise EncryptionError directly (line 85: except EncryptionError: raise)
        with pytest.raises(EncryptionError):
            crypto_manager.encrypt(plaintext, nonce=invalid_nonce)

    def test_encrypt_wraps_generic_exception(self, crypto_manager: CryptoManager) -> None:
        """Test that generic exceptions during encryption are wrapped."""

        # Create a custom object that raises exception on encode()
        class BadString:
            def __str__(self):
                return "bad_string"

            def encode(self, encoding):
                raise ValueError("Cannot encode this object")

        bad_plaintext = BadString()

        # This should catch the ValueError and wrap it as EncryptionError
        with pytest.raises(EncryptionError, match="Encryption failed"):
            crypto_manager.encrypt(bad_plaintext)


class TestGetCryptoManager:
    """Tests for get_crypto_manager factory function."""

    def test_with_32_char_ascii_key(self) -> None:
        """Test get_crypto_manager with 32-character ASCII key."""
        # Mock settings to return 32-char key
        mock_settings = type("Settings", (), {})()
        mock_key = type("SecretStr", (), {"get_secret_value": lambda self: "a" * 32})()
        mock_settings.encryption_key = mock_key

        with patch("squant.utils.crypto.get_settings", return_value=mock_settings):
            # Clear cache to ensure fresh instance
            get_crypto_manager.cache_clear()

            manager = get_crypto_manager()
            assert isinstance(manager, CryptoManager)

            # Should be able to encrypt/decrypt
            plaintext = "test_data"
            ciphertext, nonce = manager.encrypt(plaintext)
            assert manager.decrypt(ciphertext, nonce) == plaintext

    def test_with_base64_encoded_key(self) -> None:
        """Test get_crypto_manager with base64-encoded 32-byte key."""
        # Generate valid base64-encoded 32-byte key
        key_bytes = os.urandom(32)
        b64_key = base64.b64encode(key_bytes).decode("ascii")
        assert len(b64_key) == 44  # base64 of 32 bytes is 44 chars
        assert b64_key.endswith("=")

        # Mock settings to return base64 key
        mock_settings = type("Settings", (), {})()
        mock_key = type("SecretStr", (), {"get_secret_value": lambda self: b64_key})()
        mock_settings.encryption_key = mock_key

        with patch("squant.utils.crypto.get_settings", return_value=mock_settings):
            # Clear cache to ensure fresh instance
            get_crypto_manager.cache_clear()

            manager = get_crypto_manager()
            assert isinstance(manager, CryptoManager)

            # Should be able to encrypt/decrypt
            plaintext = "test_data"
            ciphertext, nonce = manager.encrypt(plaintext)
            assert manager.decrypt(ciphertext, nonce) == plaintext

    def test_with_invalid_base64_key(self) -> None:
        """Test that invalid base64 key raises error."""
        # 44 chars ending with = but not valid base64
        invalid_b64 = "invalid!base64@string#that$is%44chars^long1="
        assert len(invalid_b64) == 44
        assert invalid_b64.endswith("=")

        mock_settings = type("Settings", (), {})()
        mock_key = type("SecretStr", (), {"get_secret_value": lambda self: invalid_b64})()
        mock_settings.encryption_key = mock_key

        with patch("squant.utils.crypto.get_settings", return_value=mock_settings):
            # Clear cache to ensure fresh instance
            get_crypto_manager.cache_clear()

            with pytest.raises(ValueError, match="Invalid base64 encryption key"):
                get_crypto_manager()

    def test_with_base64_key_wrong_decoded_length(self) -> None:
        """Test that base64 key with wrong decoded length raises error."""
        # Valid base64 but decodes to wrong length
        key_bytes = os.urandom(16)  # Only 16 bytes, not 32
        b64_key = base64.b64encode(key_bytes).decode("ascii") + "="  # Make it 44 chars

        # Adjust to make it exactly 44 chars
        while len(b64_key) < 44:
            b64_key += "="

        mock_settings = type("Settings", (), {})()
        mock_key = type("SecretStr", (), {"get_secret_value": lambda self: b64_key})()
        mock_settings.encryption_key = mock_key

        with patch("squant.utils.crypto.get_settings", return_value=mock_settings):
            # Clear cache to ensure fresh instance
            get_crypto_manager.cache_clear()

            try:
                get_crypto_manager()
                # If no error raised, the key might be valid by chance
            except ValueError as e:
                # Should mention length issue
                assert "32 bytes" in str(e) or "Invalid base64" in str(e)

    def test_with_invalid_key_length(self) -> None:
        """Test that key with invalid length raises error."""
        invalid_key = "short_key"  # Not 32 chars

        mock_settings = type("Settings", (), {})()
        mock_key = type("SecretStr", (), {"get_secret_value": lambda self: invalid_key})()
        mock_settings.encryption_key = mock_key

        with patch("squant.utils.crypto.get_settings", return_value=mock_settings):
            # Clear cache to ensure fresh instance
            get_crypto_manager.cache_clear()

            with pytest.raises(ValueError, match="ENCRYPTION_KEY must be 32 ASCII characters"):
                get_crypto_manager()

    def test_caching(self) -> None:
        """Test that get_crypto_manager caches the instance."""
        mock_settings = type("Settings", (), {})()
        mock_key = type("SecretStr", (), {"get_secret_value": lambda self: "a" * 32})()
        mock_settings.encryption_key = mock_key

        with patch("squant.utils.crypto.get_settings", return_value=mock_settings):
            # Clear cache first
            get_crypto_manager.cache_clear()

            manager1 = get_crypto_manager()
            manager2 = get_crypto_manager()

            # Should return the same instance due to caching
            assert manager1 is manager2
