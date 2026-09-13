# Screenshots wanted here

`USER_GUIDE.md` references these two images by filename. I couldn't save
real screenshots to disk automatically (the tool that renders them shows
you the image in chat, but doesn't hand me a file to write) — so the guide
currently shows a broken-image icon in their place on GitHub. Drop in your
own and they'll appear automatically, no other changes needed:

| Filename | What to capture |
|---|---|
| `litellm-login.png` | `http://localhost:4000` — the LiteLLM login screen (before logging in) |
| `litellm-dashboard.png` | After logging in (username `admin`, password your `LITELLM_MASTER_KEY`) — the main dashboard with the left sidebar visible |

Nice-to-haves if you want to expand the guide further — same idea, just
add the `![...](images/filename.png)` line in `USER_GUIDE.md` wherever
you'd like it:

- `mcp-servers-page.png` — sidebar → **MCP Servers**
- `models-page.png` — sidebar → **Models + Endpoints**
- `kilo-code-providers.png` — VS Code, Kilo Code Settings → **Providers**
- `kilo-code-model-per-mode.png` — VS Code, Kilo Code Settings → **Models**
  → "Model per Mode"
- `vscode-status-bar.png` — the bottom-right status bar showing the
  provider balance extension
