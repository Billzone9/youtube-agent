# Provider-error standard — carry the upstream message through; never substitute a guess

Established 2026-08-03, the hard way. Companion to the other standards.

## The rule
**Any provider client that raises on an error response MUST carry the upstream provider's own message
through in the exception. NEVER replace an upstream error with our assumption about its cause.**

A client may *add* an interpretation or a suggested action ("…the token may lack the force-ssl scope"),
but only *alongside* the raw upstream message — never *instead of* it, and never asserted as fact when
the provider didn't say it. If you must guess, hedge ("may"/"likely") and still print what the provider
actually returned so the reader can see past the guess.

## Why (the hour this cost)
ElevenLabs returned `401 {"code":"quota_exceeded", "…API key quota of 15000. You have 686 credits
remaining, while 756 required…"}` on beat 3 of a production. Our client **discarded the body and
substituted a fixed string**: *"the key likely lacks the Text-to-Speech scope."* That single wrong
substitution sent the diagnosis through **four wrong theories** — missing scope, account quota,
rate-limiting, transient blip — before the real body (a hard per-key credit cap) was finally read
directly from the API. The provider had told us the exact cause and the exact numbers in the first
response; we threw them away and guessed. Reading the body would have ended it in one step.

## How it's enforced (the audit, 2026-08-03)
- **ElevenLabs TTS** (`ytagent/tts/elevenlabs.py`) — FIXED: parses the 401 body; `quota_exceeded` →
  `TTSQuotaError` with the real message + numbers; other 401/403 → `TTSScopeError` with the real body.
- **Anthropic** (`ytagent/providers/anthropic_provider.py`) — OK: uses the SDK, whose `APIError`
  subclasses already carry the upstream message; we let them propagate, no substitution.
- **Pexels / Pixabay** (`ytagent/sourcing/{pexels,pixabay}.py`) & **download** (`sourcing/download.py`)
  — FIXED: bare `raise_for_status()` raised the status line but dropped the body; now raise via
  `ytagent/httpx_error.py:raise_for_status_with_body`, which appends the response body.
- **YouTube** (`ytagent/youtube.py:_http_error`) — FIXED: it extracted only `reason` and asserted a
  scope guess when `reason` was empty; now it carries the upstream **message** through and only *adds*
  the scope hint (hedged), never replaces the message with it.

## Doctrine for new clients
When you write any client that raises on a non-2xx (or SDK) error:
1. **Read the body** (`r.text` / `r.json()` / the SDK error's message) and include it in the exception.
2. **Classify by the provider's OWN codes** (`quota_exceeded`, `reason`, etc.), not by our theory of
   what a status code "usually means".
3. Add a suggested human action if useful, **after** the raw message, hedged if it is a guess.
4. Use `ytagent/httpx_error.py:raise_for_status_with_body` for raw httpx clients instead of the bare
   `raise_for_status()` — it never drops the body.
