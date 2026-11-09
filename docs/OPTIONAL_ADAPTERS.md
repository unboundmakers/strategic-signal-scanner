# Optional Model and Notification Adapters

The primary Google Cloud path uses Gemini through the Vertex SDK backend and
ADC. These adapters remain available without changing the capture, score and
JSON output contracts. All live examples require explicit authorization, access to
the input material, suitable credentials and an operator-reviewed configuration.
They may incur provider/network charges; none runs in the container default.

## DeepSeek

[signal_replay.py](../tools/signal_replay.py) contains the actual HTTPS chat
completion adapter. It uses `DEEPSEEK_API_KEY`, optional `DEEPSEEK_BASE_URL`
and the selected model. The default model identifier is `deepseek-chat`;
validate current provider availability independently before use.

Supply the API key through a controlled environment or secret injection, never
in source, command arguments or output artifacts. Given an existing raw capture:

```sh
SCANNER_LOAD_ENV=0 DEEPSEEK_MODEL='<supported-model-id>' \
python3 -B tools/score_raw_rss.py /tmp/scanner-live/raw_YYYY-MM-DD.json \
  --mode deepseek --retry-attempts 3 --min-score 4
```

On Cloud Run, intentionally change `SCORE_MODE=deepseek`, set `DEEPSEEK_MODEL`
and inject `DEEPSEEK_API_KEY` from an operator-provisioned Secret Manager secret.
The runtime account needs accessor rights on that specific secret. Do not
configure `MODEL` to a Gemini identifier when switching providers.

The adapter uses bounded retries for retryable transport/provider failures.
The shared normalizer preserves captured metadata and bounds scores; neither
the external provider nor this normalization guarantees factual accuracy.

## Gemini API-key Backend

The same module also supports `GEMINI_BACKEND=api_key`, with `GEMINI_API_KEY`
and `GEMINI_MODEL`. This is distinct from the primary service-account ADC path.
The SDK implementation has a REST fallback for specified SDK request failures;
the Vertex backend does not use that API-key fallback.

```sh
SCANNER_LOAD_ENV=0 GEMINI_BACKEND=api_key \
GEMINI_MODEL='<supported-model-id>' \
python3 -B tools/score_raw_rss.py /tmp/scanner-live/raw_YYYY-MM-DD.json \
  --mode gemini --retry-attempts 3 --min-score 4
```

Provide `GEMINI_API_KEY` separately in the controlled process environment.
For a cloud deployment, use a specific secret rather than a literal key in
`--set-env-vars`. Switching back to Vertex requires explicit backend, project,
location and IAM configuration, not just a different model name.

## SMTP

[mailer.py](../mailer.py) supports an explicitly enabled SMTP summary notification.
`MAIL_BACKEND=disabled` is the default. To opt in, supply `MAIL_BACKEND=smtp`,
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM` and
`MAIL_TO` through the operator's environment. `SMTP_USE_TLS=true` uses STARTTLS;
it is not implicit SMTPS on port 465.

No subscriber list or sender credentials are bundled. This is a standalone
utility: the JSON-only batch job and container default do not call it. An explicit
caller supplies the message and handles errors; there are no generated report
or archive links. SMTP is an external integration, not
a Google Cloud email-delivery service.

## Authentication Boundaries

Vertex ADC, provider API keys and SMTP passwords serve different purposes. Do not share credentials between them or embed
any credential in result JSON or source links. The [technical guide](TECHNICAL_GUIDE.md)
documents the full configuration, private persistence and output boundary.
