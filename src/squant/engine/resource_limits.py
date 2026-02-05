"""Resource limits for strategy execution (STR-013).

This module provides CPU time and memory limits for strategy code execution
to prevent DoS attacks through infinite loops or excessive memory allocation.

Usage:
    from squant.engine.resource_limits import resource_limiter, ResourceLimitExceededError

    try:
        with resource_limiter(cpu_seconds=30, memory_mb=2048):
            strategy.on_bar(bar)
    except ResourceLimitExceededError as e:
        handle_error(e)

Platform Support:
    - Linux/Unix: Full support using `resource` module (setrlimit)
    - Windows: No-op (resource limits not available)
"""

import logging
import platform
import signal
from collections.abc import Generator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Check if we're on a platform that supports resource limits
_IS_UNIX = platform.system() in ("Linux", "Darwin")

if _IS_UNIX:
    import resource


class ResourceLimitExceededError(Exception):
    """Base exception for resource limit violations."""

    pass


class CPUTimeoutError(ResourceLimitExceededError):
    """Raised when strategy execution exceeds CPU time limit."""

    pass


class MemoryLimitError(ResourceLimitExceededError):
    """Raised when strategy execution exceeds memory limit."""

    pass


def _timeout_handler(signum: int, frame: object) -> None:
    """Signal handler for CPU timeout."""
    raise CPUTimeoutError("Strategy execution exceeded CPU time limit")


@contextmanager
def resource_limiter(
    cpu_seconds: int = 30,
    memory_mb: int = 2048,
) -> Generator[None, None, None]:
    """Context manager that limits CPU time and memory usage.

    This enforces resource limits on the code block to prevent:
    - Infinite loops (CPU time limit)
    - Memory exhaustion attacks (memory limit via RLIMIT_AS)

    Note: RLIMIT_AS limits the entire process's virtual address space.
    The default of 2048MB provides enough headroom for the Python runtime
    and libraries while still preventing runaway memory allocation by
    strategy code.

    Args:
        cpu_seconds: Maximum CPU time in seconds. Default 30s.
        memory_mb: Maximum memory in megabytes. Default 2048MB.

    Yields:
        None

    Raises:
        CPUTimeoutError: If the code block exceeds CPU time limit.
        MemoryLimitError: If memory allocation fails due to limit.

    Note:
        On some environments (Docker containers, restrictive systems),
        resource limits may not be settable. In such cases, the limiter
        operates as a no-op with a warning logged.

    Example:
        >>> with resource_limiter(cpu_seconds=5, memory_mb=2048):
        ...     # Strategy code runs here with limits enforced
        ...     strategy.on_bar(bar)
    """
    if not _IS_UNIX:
        # On Windows, just yield without limits
        logger.debug("Resource limits not available on this platform, skipping")
        yield
        return

    # Track what we need to restore
    limits_set = False
    old_cpu_soft = old_cpu_hard = None
    old_as_soft = old_as_hard = None
    old_handler = None

    try:
        # Save original limits and handler
        old_cpu_soft, old_cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
        old_as_soft, old_as_hard = resource.getrlimit(resource.RLIMIT_AS)
        old_handler = signal.signal(signal.SIGXCPU, _timeout_handler)

        # Calculate new limits
        memory_bytes = memory_mb * 1024 * 1024

        # Try to set CPU time limit
        # In some environments (containers), we may not be able to change limits
        try:
            # Only set if we're lowering the limit or if there's no limit
            if old_cpu_hard == resource.RLIM_INFINITY or cpu_seconds <= old_cpu_hard:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
            else:
                logger.warning(
                    f"Cannot set CPU limit to {cpu_seconds}s (hard limit is {old_cpu_hard}s)"
                )
        except (ValueError, OSError) as e:
            logger.warning(f"Cannot set CPU time limit: {e}")

        # Try to set address space (virtual memory) limit
        try:
            if old_as_hard == resource.RLIM_INFINITY or memory_bytes <= old_as_hard:
                resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            else:
                logger.warning(f"Cannot set memory limit to {memory_mb}MB (hard limit applies)")
        except (ValueError, OSError) as e:
            logger.warning(f"Cannot set memory limit: {e}")

        limits_set = True
        logger.debug(f"Resource limits set: CPU={cpu_seconds}s, memory={memory_mb}MB")

        yield

    except MemoryError as e:
        # Convert to our custom error for consistent handling
        raise MemoryLimitError(f"Strategy execution exceeded memory limit ({memory_mb}MB)") from e
    finally:
        # Restore original limits if we set them
        if limits_set:
            if old_handler is not None:
                signal.signal(signal.SIGXCPU, old_handler)
            if old_cpu_soft is not None and old_cpu_hard is not None:
                try:
                    resource.setrlimit(resource.RLIMIT_CPU, (old_cpu_soft, old_cpu_hard))
                except (ValueError, OSError):
                    pass  # Best effort restoration
            if old_as_soft is not None and old_as_hard is not None:
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (old_as_soft, old_as_hard))
                except (ValueError, OSError):
                    pass  # Best effort restoration
            logger.debug("Resource limits restored to original values")


def is_resource_limiting_supported() -> bool:
    """Check if resource limiting is supported on this platform.

    Returns:
        True if resource limits can be enforced, False otherwise.
    """
    return _IS_UNIX
