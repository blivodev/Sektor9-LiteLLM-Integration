"""
Sektor9 LiteLLM credit-exhaustion failover patch (sitecustomize).

PROBLEM (reproduced & proven live): when a provider runs out of credits, the
request must transparently fail over to the next-cheapest healthy provider.
LiteLLM does NOT do that out of the box, for two reasons:

  1. HTTP 402 "Insufficient Balance" is mapped to a generic `APIError`, which
     the router neither retries across deployments nor cools down.
     (Originally reported against DeepInfra.)

  2. Fireworks AI does NOT use 402. When the account is over its monthly spend
     limit / suspended, the Fireworks API returns **HTTP 412 Precondition
     Failed** with a body like:
         {"error":{"message":"Account <name> is suspended, possibly due to
          reaching the monthly spending limit or failure to pay past
          invoices...","code":"PRECONDITION_FAILED","type":"error"}}
     LiteLLM falls 412 through to a non-retriable exception (BadRequestError /
     APIError). Confirmed live: a request pinned to a Fireworks-only leg died
     hard with `litellm.APIError: APIError: Fireworks_aiException - {... 412
     PRECONDITION_FAILED ...}` and "No fallback model group found", instead of
     stepping to the next provider. This is the "Fireworks ran out of credits
     and nothing fell back" incident.

FIX: patch `_map_openai_exception`, `_map_openai_like_exception`,
`_map_openrouter_exception` and the status-based `_map_exception_by_status` so
that a credit-exhaustion error maps to `RateLimitError` instead of a generic
`APIError`/`BadRequestError`. RateLimitError is retriable across deployments
AND triggers cooldown of the failing deployment, so the router fails over to
the next-cheapest healthy provider the instant one provider runs out of
credits.

Which errors are treated as credit-exhaustion:
  - ANY status with an "insufficient balance / insufficient credits / out of
    credits / quota exceeded / billing" signal in the body.
  - HTTP 402 unconditionally (402 means "payment required" by definition).
  - HTTP 412 ONLY when the body also carries an account/billing signal
    ("suspended", "spending limit", "past invoice", "billing", "payment"), so a
    genuine client-side Precondition Failed still surfaces as itself.

Applied via Python's `sitecustomize` hook (auto-imported at interpreter start,
before litellm loads), so it survives container restarts without touching the
upstream package. Idempotent: re-running is a no-op.
"""
from __future__ import annotations

import re

# Substrings (lower-cased) that mark an error as a billing / credit problem
# rather than a malformed request. Kept deliberately specific for the generic
# scan; the 412 branch additionally keys off the account-scoped words below.
_CREDIT_SIGNALS = (
    "insufficient balance",
    "insufficient credit",
    "insufficient_quota",
    "insufficient quota",
    "out of credits",
    "out of credit",
    "not enough credits",
    "exceeded your current quota",
    "quota exceeded",
    "credit limit",
    "spending limit",
    "monthly spending limit",
    "past invoice",
    "payment required",
    "billing",
    "please go to",  # Fireworks' body always ends "...go to <billing url>"
    "account is suspended",
    "account suspended",
)

# For a 412 we require one of these account-level words, so an ordinary
# precondition failure is never mistaken for a dead account.
_ACCOUNT_412_SIGNALS = (
    "suspended",
    "spending limit",
    "past invoice",
    "billing",
    "payment",
    "insufficient",
    "out of credit",
    "quota",
)


def _patch():
    import litellm  # noqa: PLC0415
    emu = litellm.litellm_core_utils.exception_mapping_utils

    # Guard: already patched (marker set below).
    if getattr(emu, "_sektor9_402_patched", False):
        return

    def _status(exc):
        return getattr(exc, "status_code", None)

    def _raw_text(exc, error_str, extra_information):
        """Best-effort collection of everything the provider said."""
        parts = [error_str or "", extra_information or ""]
        for attr in ("message", "body"):
            val = getattr(exc, attr, None)
            if val:
                parts.append(str(val))
        resp = getattr(exc, "response", None)
        if resp is not None:
            try:
                parts.append(str(resp.text))  # httpx response body
            except Exception:  # noqa: BLE001
                pass
        return " ".join(parts).lower()

    def _is_credit_exhaustion(exc, error_str, extra_information) -> bool:
        """True when the provider refused the call because the account is out
        of credits / suspended -- i.e. a failover-worthy, cooldown-worthy
        condition rather than a malformed request."""
        st = _status(exc)
        text = _raw_text(exc, error_str, extra_information)

        # 402 is "Payment Required" by definition: always a credit problem.
        if st == 402:
            return True

        # 412 is overloaded, so only treat it as credit-exhaustion when the
        # body names an account/billing condition. Fireworks' suspended-account
        # 412 matches here.
        if st == 412:
            return any(sig in text for sig in _ACCOUNT_412_SIGNALS)

        # Otherwise: any status, but only with an explicit billing signal.
        return any(sig in text for sig in _CREDIT_SIGNALS)

    def _raise_as_rate_limit(exception_provider, message, model, custom_llm_provider, original_exception, extra_information):
        from litellm import RateLimitError
        raise RateLimitError(
            message=f"RateLimitError: {exception_provider} - {message}",
            model=model,
            llm_provider=custom_llm_provider,
            response=getattr(original_exception, "response", None),
            litellm_debug_info=extra_information,
        )

    def _wrap(orig):
        def _patched(**kw):
            oe = kw.get("original_exception")
            if oe is not None and _is_credit_exhaustion(
                oe, kw.get("error_str"), kw.get("extra_information")
            ):
                _raise_as_rate_limit(
                    kw.get("exception_provider"), kw.get("error_str"),
                    kw.get("model"), kw.get("custom_llm_provider"), oe,
                    kw.get("extra_information"),
                )
            return orig(**kw)
        return _patched

    # ---- 1) _map_openai_exception (openai / deepinfra / fireworks_ai / custom_openai) ----
    emu._map_openai_exception = _wrap(emu._map_openai_exception)

    # ---- 2) _map_openai_like_exception (predibase, databricks, lemonade, watsonx, ...) ----
    if hasattr(emu, "_map_openai_like_exception"):
        emu._map_openai_like_exception = _wrap(emu._map_openai_like_exception)

    # ---- 3) _map_openrouter_exception ----
    if hasattr(emu, "_map_openrouter_exception"):
        emu._map_openrouter_exception = _wrap(emu._map_openrouter_exception)

    # ---- 4) generic status-based mapper (safety net for any provider) ----
    if hasattr(emu, "_map_exception_by_status"):
        emu._map_exception_by_status = _wrap(emu._map_exception_by_status)

    emu._sektor9_402_patched = True
    import logging
    logging.getLogger("LiteLLM").warning(
        "Sektor9 credit-exhaustion failover patch applied (402 + account-level 412 -> RateLimitError)"
    )


try:
    _patch()
except Exception:  # noqa: BLE001 - never break proxy startup because of the patch
    import traceback
    traceback.print_exc()
