# Extends the official LiteLLM image with the runtimes its own base image
# (a minimal Wolfi Linux) doesn't ship: npm (for npx-launched MCP servers)
# and pip (for Python-based ones). Node and python3 are already present.
FROM ghcr.io/berriai/litellm:main-latest

RUN apk add --no-cache npm py3-pip ffmpeg git go

# LiteLLM's own python3 on PATH is an isolated venv without pip; install uv
# (the standard way most Python MCP servers are run, via `uvx <package>`,
# no separate pip-install step needed) using the system pip explicitly.
RUN /usr/bin/pip3 install --break-system-packages --no-cache-dir uv

# mcp-language-server (LSP bridge covering Go/Python/JS/C# in one server)
# is Go-only with no published binary release — compile it at build time so
# the running container doesn't need Go/network access to use it.
ENV GOPATH=/opt/go
ENV PATH="${GOPATH}/bin:${PATH}"
RUN go install github.com/isaacphi/mcp-language-server@latest

# gopls, so mcp-language-server has at least one real LSP to bridge for Go
# out of the box (point it at pyright/typescript-language-server/OmniSharp
# the same way for other languages — just more `go install`/`npm i -g`).
RUN go install golang.org/x/tools/gopls@latest

# ffmpeg-mcp (misbahsy/video-audio-mcp) isn't published as an installable
# package — clone it and let uv resolve its own deps at build time.
RUN git clone --depth 1 https://github.com/misbahsy/video-audio-mcp /opt/video-audio-mcp \
    && cd /opt/video-audio-mcp \
    && uv sync --frozen || uv sync

# LiteLLM's stdio MCP launcher only reliably registers `command: npx` or
# `command: uvx` — anything else (a direct binary path, bare `uv`, `sh`)
# fails to register with zero log output (found the hard way). This tiny
# local "npm package" lets any real command masquerade as an npx one:
# `npx -y /opt/npx-shim <real-command> <real-args...>` just execs them.
RUN mkdir -p /opt/npx-shim && \
    printf '{"name":"npx-shim","version":"1.0.0","bin":{"npx-shim":"./bin.js"}}' > /opt/npx-shim/package.json && \
    printf '#!/usr/bin/env node\nconst { spawnSync } = require("child_process");\nconst [cmd, ...rest] = process.argv.slice(2);\nconst r = spawnSync(cmd, rest, { stdio: "inherit" });\nprocess.exit(r.status ?? 1);\n' > /opt/npx-shim/bin.js && \
    chmod +x /opt/npx-shim/bin.js
