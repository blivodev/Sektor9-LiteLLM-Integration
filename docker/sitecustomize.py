"""
Sektor9 LiteLLM provider-failure failover patch (sitecustomize).

GOAL: when a provider cannot serve a request because the *account* is the
problem -- out of credits, over a spending/budget limit, rate-limited,
suspended, or otherwise refusing to do inference -- the request must
transparently fail over to the next-cheapest HEALTHY provider. LiteLLM does
not do this out of the box; it fails hard on several of these signals.

Reproduced live (each one killed a request instead of failing over):

  1. DeepInfra  HTTP 402 "You need positive balance to do inference"
     -> generic APIError(402); not retried, not cooled down.

  2. Fireworks  HTTP 412 PRECONDITION_FAILED "Account <name> is suspended,
     possibly due to reaching the monthly spending limit or failure to pay
     past invoices..."
     -> generic APIError(412) + "No fallback model group found".

  3. OpenRouter HTTP 403 {"error":{"message":"Budget limit exceeded (monthly
     limit). $40.06 of $40.00 used; resets ...","code":403,
     "metadata":{"limit_source":"openrouter_guardrail_budget",...}}}
     -> generic APIError(403); not retried, not cooled down.  <-- the gap that
     made failover look "inconsistent": the dead provider kept rejoining
     rotation because it was never cooled down.

Also relevant, LiteLLM's own defaults (verified in 1.102.0):
  - DEFAULT_COOLDOWN_TIME_SECONDS = 5  (a dead provider returns after 5s)
  - litellm.allowed_fails = 3          (3 failures/min before cooldown)
  - _should_retry() retries only 408/409/429/5xx
  - _is_cooldown_required() cools down only 429/401/408/404 among 4xx
So even the errors LiteLLM *does* understand leave the provider back in
rotation within seconds. The config sets cooldown_time / allowed_fails (see
config.yaml router_settings) and this patch makes the *account-level*
failures retriable + cooldown-worthy in the first place.

FIX: wrap the provider exception mappers so any error whose body names a
billing / credit / quota / budget / rate-limit / suspension condition maps to
`RateLimitError`. RateLimitError is retriable across deployments AND triggers
cooldown of the failing deployment, so the router skips the dead provider and
lands on the next-cheapest healthy one.

Which errors are treated as provider failure:
  - HTTP 402 unconditionally ("Payment Required" by definition).
  - HTTP 403 / 412 ONLY when the body carries an account-scoped word
    (budget / limit / quota / credit / balance / billing / payment / invoice /
    suspend / spending / unpaid / rate / capacity / overloaded), so a genuine
    authorization or precondition failure still surfaces as itself.
  - ANY status carrying an explicit credit / billing / quota / budget /
    rate-limit / capacity signal in the body.

Applied via Python's `sitecustomize` hook (auto-imported at interpreter start,
before litellm loads), so it survives container restarts without touching the
upstream package. Idempotent: re-running is a no-op.
"""
from __future__ import annotations

# Substrings (lower-cased) that mark an error as an ACCOUNT / provider-capacity
# problem rather than a malformed request. Matched against the whole error text
# (message + body + response body), so it works regardless of the HTTP status
# the provider chose.
_CREDIT_SIGNALS = (
    # --- credits / balance ---
    "insufficient balance",
    "insufficient credit",
    "insufficient_quota",
    "insufficient quota",
    "out of credits",
    "out of credit",
    "not enough credits",
    "no credit",
    "credit limit",
    "credit balance",
    "positive balance",
    "add balance",
    "top up",
    "top-up",
    "balance is too low",
    "low balance",
    # --- quota / usage ---
    "exceeded your current quota",
    "quota exceeded",
    "quota exhausted",
    "usage limit",
    "limit reached",
    "limit exceeded",
    "exceeded the limit",
    # --- budget / spending ---
    "budget limit",
    "budget exceeded",
    "budget has been exceeded",
    "monthly limit",
    "monthly budget",
    "spending limit",
    "monthly spending limit",
    # --- billing / payment / suspension ---
    "past invoice",
    "payment required",
    "payment failed",
    "unpaid",
    "billing",
    "account is suspended",
    "account suspended",
    "suspended",
    "please go to",  # Fireworks' body always ends "...go to <billing url>"
    # --- rate limiting / capacity (some providers return these as non-429) ---
    "rate limit",
    "rate-limit",
    "too many requests",
    "requests per",
    "tokens per",
    "overloaded",
    "at capacity",
    "no capacity",
    "capacity exceeded",
    "temporarily unavailable",
    "provider is down",
)

# For 403/412 we require one of these account-scoped words, so an ordinary
# authorization / precondition failure is never mistaken for a dead account.
_ACCOUNT_SIGNALS = (
    "budget",
    "limit",
    "quota",
    "credit",
    "balance",
    "billing",
    "payment",
    "invoice",
    "suspend",
    "spending",
    "unpaid",
    "rate",
    "capacity",
    "overloaded",
)


def _patch():
    import litellm  # noqa: PLC0415
    emu = litellm.litellm_core_utils.exception_mapping_utils

    # Guard: already patched (marker set below).
    if getattr(emu, "_sektor9_provider_failover_patched", False):
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

    def _is_provider_failure(exc, error_str, extra_information) -> bool:
        """True when the provider refused the call for an account / capacity
        reason -- i.e. a failover-worthy, cooldown-worthy condition rather than
        a malformed request."""
        st = _status(exc)
        text = _raw_text(exc, error_str, extra_information)

        # 402 is "Payment Required" by definition: always a credit problem.
        if st == 402:
            return True

        # 403/412 are overloaded: only treat them as account-level when the
        # body names a billing/quota/limit/capacity condition. (A genuine
        # "no access to this model" 403 or a malformed-request 412 is left
        # to surface as itself.)
        if st in (403, 412):
            return any(sig in text for sig in _ACCOUNT_SIGNALS)

        # Otherwise: any status (incl. 429, 5xx, or a mislabelled 4xx) carrying
        # an explicit credit/billing/quota/rate signal is failover-worthy.
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
            if oe is not None and _is_provider_failure(
                oe, kw.get("error_str"), kw.get("extra_information")
            ):
                _raise_as_rate_limit(
                    kw.get("exception_provider"), kw.get("error_str"),
                    kw.get("model"), kw.get("custom_llm_provider"), oe,
                    kw.get("extra_information"),
                )
            return orig(**kw)
        return _patched

    # ---- OpenAI-compatible path (openai / deepinfra / fireworks_ai / custom_openai / ...) ----
    emu._map_openai_exception = _wrap(emu._map_openai_exception)

    # ---- every other provider mapper that exists in this build ----
    for _name in (
        "_map_openai_like_exception",
        "_map_openrouter_exception",
        "_map_exception_by_status",
        "_map_azure_exception",
        "_map_anthropic_exception",
        "_map_gemini_exception",
        "_map_bedrock_exception",
        "_map_vertex_ai_exception",
        "_map_mistral_exception",
        "_map_groq_exception",
    ):
        _orig = getattr(emu, _name, None)
        if _orig is not None and callable(_orig):
            setattr(emu, _name, _wrap(_orig))

    emu._sektor9_provider_failover_patched = True
    import logging
    logging.getLogger("LiteLLM").warning(
        "Sektor9 provider-failure failover patch applied "
        "(credit/budget/quota/rate/suspension errors -> RateLimitError)"
    )


try:
    _patch()
except Exception:  # noqa: BLE001 - never break proxy startup because of the patch
    import traceback
    traceback.print_exc()
