"""Unit tests for RiskState model — circuit breaker consecutive_losses bug."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from squant.engine.risk.models import RiskState


class TestCircuitBreakerPreservesConsecutiveLosses:
    """Test that circuit breaker cooldown expiry does NOT reset consecutive_losses.

    Bug M-2: check_circuit_breaker_expired() used to reset consecutive_losses to 0
    when cooldown expired. This allows a systematically losing strategy to accumulate
    N more losses before re-triggering, causing unnecessary additional losses.
    The fix preserves consecutive_losses so a single subsequent loss immediately
    re-triggers the circuit breaker.
    """

    def test_consecutive_losses_preserved_after_circuit_breaker_expires(self):
        """After circuit breaker cooldown expires, consecutive_losses must NOT be reset."""
        state = RiskState()

        # Simulate 5 consecutive losses
        for _ in range(5):
            state.record_trade(Decimal("-100"))
        assert state.consecutive_losses == 5

        # Trigger circuit breaker with a short cooldown
        state.trigger_circuit_breaker(cooldown_minutes=1)
        assert state.circuit_breaker_triggered is True
        assert state.consecutive_losses == 5

        # Simulate cooldown expiration by setting breaker_until in the past
        state.circuit_breaker_until = datetime.now(UTC) - timedelta(minutes=2)

        # Check expiration — should return True (expired)
        expired = state.check_circuit_breaker_expired()
        assert expired is True

        # The bug: consecutive_losses was reset to 0 here.
        # After fix, consecutive_losses must remain at 5.
        assert state.consecutive_losses == 5

    def test_circuit_breaker_state_cleared_but_losses_kept(self):
        """Breaker flags are cleared on expiry but loss count remains."""
        state = RiskState()

        for _ in range(3):
            state.record_trade(Decimal("-200"))
        assert state.consecutive_losses == 3

        state.trigger_circuit_breaker(cooldown_minutes=1)
        state.circuit_breaker_until = datetime.now(UTC) - timedelta(seconds=1)

        state.check_circuit_breaker_expired()

        # Breaker flags should be cleared
        assert state.circuit_breaker_triggered is False
        assert state.circuit_breaker_until is None

        # But consecutive losses must be preserved
        assert state.consecutive_losses == 3

    def test_single_loss_after_cooldown_retriggers_if_at_threshold(self):
        """If consecutive_losses == threshold after cooldown, one more loss re-triggers."""
        threshold = 3
        state = RiskState()

        # Build up to threshold
        for _ in range(threshold):
            state.record_trade(Decimal("-50"))
        assert state.consecutive_losses == threshold

        # Trigger and expire breaker
        state.trigger_circuit_breaker(cooldown_minutes=1)
        state.circuit_breaker_until = datetime.now(UTC) - timedelta(minutes=5)
        state.check_circuit_breaker_expired()

        # One more loss pushes above threshold
        state.record_trade(Decimal("-50"))
        assert state.consecutive_losses == threshold + 1
