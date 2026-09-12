# LiteLLM Provider Balance (local, unpublished)

A tiny status bar extension — not on the Marketplace, just dropped straight
into your VS Code extensions folder — showing remaining credit for the
providers behind your LiteLLM proxy.

## What it shows

Bottom-right status bar: `$(credit-card) OR $12.34 · DI $45.67 · FW ↗`

- **OpenRouter** — real remaining credit, via their documented
  `GET /api/v1/credits` endpoint (`total_credits - total_usage`).
- **DeepInfra** — via `GET /v1/me?checklist=true`'s `stripe_balance` field.
  Note DeepInfra's sign convention: **negative = ready-to-spend credit**,
  positive = amount owed. The status bar shows it correctly either way.
- **Fireworks AI** — has no public "remaining balance" API (only itemized
  billing-period line items), so this is just a `↗` link to their billing
  dashboard rather than a faked number.

Click the status bar item for a menu: refresh now, set/update either key,
or open any provider's dashboard.

## Where it gets your API keys

On refresh, it reads `OPENROUTER_API_KEY` / `DEEPINFRA_API_KEY` from a
`.env` file in your open workspace folder (i.e. this project's `.env`) —
nothing to configure. If it doesn't find one there, it'll fall back to a
key you enter via the status bar menu, stored in VS Code's encrypted
`SecretStorage` (not written to any file).

It auto-refreshes every 10 minutes, and on demand via the menu.

## Reinstalling / updating

This copy lives in the repo at `vscode-extension/litellm-provider-balance/`
for version control, but VS Code actually loads its copy from
`%USERPROFILE%\.vscode\extensions\local.litellm-provider-balance-0.0.1\`.
After editing the source here, re-copy it and reload VS Code:

```bash
DEST="$HOME/.vscode/extensions/local.litellm-provider-balance-0.0.1"
rm -rf "$DEST" && mkdir -p "$DEST"
cp package.json extension.js "$DEST/"
```

Then run **Developer: Reload Window** from VS Code's command palette.
