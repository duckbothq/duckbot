"""Failures this package raises.

Each one is a separate type because callers respond differently: an unknown price is a
configuration problem for an operator, a sensitivity ceiling is a policy problem that
must never be retried against a different provider, and an adapter failure is the only
one of the three that a fallback chain should try to recover from.
"""

from __future__ import annotations


class GatewayError(Exception):
    """Base for everything this package raises."""


class UnknownPrice(GatewayError):
    """No price is configured for a model that costs money.

    Deliberately an error rather than a zero. A gateway that silently prices an unknown
    model at nothing produces a cost report that understates the bill, and the first
    person to notice is whoever opens the invoice.
    """


class NoEligibleModel(GatewayError):
    """Nothing in the registry can take this request.

    The message names the constraint that eliminated the last candidate, because "no
    model available" without a reason is an unanswerable support ticket.
    """


class SensitivityCeilingExceeded(GatewayError):
    """An adapter was asked to handle content above what it may receive.

    This is a bug, not a condition to recover from. It must never be retried against
    another provider — the content was too sensitive for the last one, so trying a
    different one is the opposite of what should happen.
    """


class AdapterFailure(GatewayError):
    """A provider call failed. The only failure a fallback chain may act on."""
