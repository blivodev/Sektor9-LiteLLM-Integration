"""
Sektor9 LiteLLM 402 failover patch (sitecustomize).

PROBLEM (reproduced & proven): when an OpenAI-compatible provider (DeepInfra,
OpenRouter, Fireworks, custom_openai, openai) returns HTTP 402 "Insufficient
Balance" (out of credits), LiteLLM's exception mapper raises a generic
`litellm.APIError(status_code=402)`. The router's retry/cooldown logic only
treats 429/401/404/408/5xx as failover-worthy, so a 402 is NOT retried across
the other deployments and does NOT cooldown the broken one -> every request to
the credit-starved provider fails hard instead of failing over to a healthy
provider. This is exactly the "had to top up DeepInfra again" incident.

FIX: patch `_map_openai_exception`, `_map_openai_like_exception`,
`_map_openrouter_exception` and the status-based `_map_exception_by_status` so
a 402 maps to `RateLimitError` instead of `APIError`. RateLimitError is
retriable across deployments AND triggers cooldown of the failing deployment,
so the router transparently fails over to the next-cheapest healthy provider
(OpenRouter / Fireworks) the instant one provider runs out of credits.

Applied via Python's `sitecustomize` hook (auto-imported at interpreter start,
before litellm loads), so it survives container restarts without touching the
upstream package. Idempotent: re-running is a no-op.
"""
from __future__ import annotations


def _patch():
    import litellm  # noqa: PLC0415
    emu = litellm.litellm_core_utils.exception_mapping_utils

    # Guard: already patched (marker set below).
    if getattr(emu, "_sektor9_402_patched", False):
        return

    def _raise_402_as_rate_limit(exception_provider, message, model, custom_llm_provider, original_exception, extra_information):
        from litellm import RateLimitError
        raise RateLimitError(
            message=f"RateLimitError: {exception_provider} - {message}",
            model=model,
            llm_provider=custom_llm_provider,
            response=getattr(original_exception, "response", None),
            litellm_debug_info=extra_information,
        )

    def _is_402(exc) -> bool:
        return getattr(exc, "status_code", None) == 402

    # ---- 1) _map_openai_exception (openai / deepinfra / fireworks_ai / custom_openai) ----
    _orig_openai = emu._map_openai_exception

    def _patched_map_openai_exception(**kw):
        oe = kw.get("original_exception")
        if _is_402(oe):
            _raise_402_as_rate_limit(
                kw.get("exception_provider"), kw.get("error_str"),
                kw.get("model"), kw.get("custom_llm_provider"), oe, kw.get("extra_information"),
            )
        return _orig_openai(**kw)

    emu._map_openai_exception = _patched_map_openai_exception

    # ---- 2) _map_openai_like_exception (predibase, databricks, lemonade, watsonx, ...) ----
    if hasattr(emu, "_map_openai_like_exception"):
        _orig_like = emu._map_openai_like_exception

        def _patched_map_openai_like_exception(**kw):
            oe = kw.get("original_exception")
            if _is_402(oe):
                _raise_402_as_rate_limit(
                    kw.get("exception_provider"), kw.get("error_str"),
                    kw.get("model"), kw.get("custom_llm_provider"), oe, kw.get("extra_information"),
                )
            return _orig_like(**kw)

        emu._map_openai_like_exception = _patched_map_openai_like_exception

    # ---- 3) _map_openrouter_exception ----
    if hasattr(emu, "_map_openrouter_exception"):
        _orig_oor = emu._map_openrouter_exception

        def _patched_map_openrouter_exception(**kw):
            oe = kw.get("original_exception")
            if _is_402(oe):
                _raise_402_as_rate_limit(
                    kw.get("exception_provider"), kw.get("error_str"),
                    kw.get("model"), kw.get("custom_llm_provider"), oe, kw.get("extra_information"),
                )
            return _orig_oor(**kw)

        emu._map_openrouter_exception = _patched_map_openrouter_exception

    # ---- 4) generic status-based mapper (safety net for any provider) ----
    if hasattr(emu, "_map_exception_by_status"):
        _orig_status = emu._map_exception_by_status

        def _patched_map_exception_by_status(**kw):
            oe = kw.get("original_exception")
            if _is_402(oe):
                _raise_402_as_rate_limit(
                    kw.get("exception_provider"), kw.get("error_str"),
                    kw.get("model"), kw.get("custom_llm_provider"), oe, kw.get("extra_information"),
                )
            return _orig_status(**kw)

        emu._map_exception_by_status = _patched_map_exception_by_status

    emu._sektor9_402_patched = True
    import logging
    logging.getLogger("LiteLLM").warning("Sektor9 402 failover patch applied (402 -> RateLimitError)")


try:
    _patch()
except Exception:  # noqa: BLE001 - never break proxy startup because of the patch
    import traceback
    traceback.print_exc()
