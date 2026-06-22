"""Nomaya exception hierarchy.

A small, explicit set of error types so every layer can fail in a way the caller
can reason about — a transient provider hiccup is not the same as a misconfigured
model string, and the orchestrator/API treat them differently. All inherit from
`NomayaError`, so callers can catch the whole family with one except clause.
"""

from __future__ import annotations


class NomayaError(Exception):
    """Base class for every error Nomaya raises deliberately."""


class ConfigError(NomayaError):
    """Invalid configuration — a bad model string, missing key, bad env value.

    These are caller mistakes that should fail fast with a clear message rather
    than surfacing as an opaque provider failure mid-run.
    """


class ProviderError(NomayaError):
    """A model call failed. Base for the provider-level failure modes below."""


class ProviderTimeout(ProviderError):
    """The model call exceeded the configured request timeout."""


class ProviderRateLimit(ProviderError):
    """The provider rejected the call for rate-limit / quota reasons (HTTP 429)."""
