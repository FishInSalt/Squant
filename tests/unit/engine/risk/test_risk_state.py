"""Unit tests for RiskState model — circuit breaker consecutive_losses behavior."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from squant.engine.risk.models import RiskState


class TestCircuitBreakerResetsConsecutiveLosses:
    """Test that circuit breaker cooldown expiry RESETS consecutive_losses to 0.

    When cooldown expires, the strategy should get a fresh start. Keeping
    consecutive_losses at the threshold means a single subsequent loss would
    immediately re-trigger the circuit breaker, making the cooldown ineffective.
    """

    def test_consecutive_losses_reset_after_circuit_breaker_expires(self):
        """After circuit breaker cooldown expires, consecutive_losses should be 0."""
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

        # After cooldown, consecutive_losses must be reset for a fresh start
        assert state.consecutive_losses == 0

    def test_circuit_breaker_state_fully_cleared_on_expiry(self):
        """Breaker flags and loss count are all cleared on expiry."""
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

        # Consecutive losses should also be reset
        assert state.consecutive_losses == 0

    def test_losses_after_cooldown_start_fresh(self):
        """After cooldown expires, losses start counting from 0 again."""
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

        # After reset, one more loss should count as 1, not threshold+1
        state.record_trade(Decimal("-50"))
        assert state.consecutive_losses == 1
