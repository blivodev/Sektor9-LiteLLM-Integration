# Repomix Workflow Integration — Sektor9 LiteLLM

[Repomix](https://github.com/yamadashy/repomix) packages entire codebases into a single, clean, token-efficient context file (XML, Markdown, or Plain Text) with security scanning, intelligent ignore patterns, and token counting.

In the **Sektor9 LiteLLM** ecosystem, Repomix bridges your local codebase with LLM agents (Cherry Studio, Kilo Code, Claude Dev, Cursor, Zed) by providing comprehensive repository context in a single prompt or attachment.

---

## 1. Quick Start

Run the included packing script from anywhere:

### Python
```bash
# Pack current directory into repomix-output.xml
python scripts/repomix_pack.py

# Pack another project and copy directly to clipboard:
python scripts/repomix_pack.py "D:/Projects/StarVault" --copy

# Pack in Markdown format with stripped comments/empty lines (saves tokens):
python scripts/repomix_pack.py "D:/Projects/Bastion Circuit Designer" --style markdown --compress --copy
```

### PowerShell
```powershell
# Pack with XML format and copy to clipboard:
.\scripts\repomix_pack.ps1 -TargetDir "D:\Projects\StarVault" -Copy

# Pack compressed:
.\scripts\repomix_pack.ps1 -TargetDir . -Compress -Copy
```

### Direct NPX
```bash
npx -y repomix
```

---

## 2. Using Packed Code with Sektor9 Agents

Once packed, paste the output into your chat with any Sektor9 agent:

- **`sektor9-code`**: Implement new features across multiple files with full project awareness.
- **`sektor9-review`**: Audit security, architecture, performance bottlenecks, and dead code.
- **`sektor9-refactor`**: Clean up technical debt, reorganize modules, and improve type safety.
- **`sektor9-test`**: Generate comprehensive test suites covering all edge cases.
- **`sektor9-docs`**: Generate project README, API specifications, and architecture docs.
- **`sektor9-autorouter`**: Automatically selects the most cost-effective model to analyze the codebase.

---

## 3. Configuration (`repomix.config.json`)

The root `repomix.config.json` is automatically applied when packing:

```json
{
  "$schema": "https://raw.githubusercontent.com/yamadashy/repomix/main/repomix.config.json",
  "output": {
    "filePath": "repomix-output.xml",
    "style": "xml",
    "parsableStyle": true,
    "fileSummary": true,
    "directoryStructure": true,
    "removeComments": false,
    "removeEmptyLines": true,
    "topFilesLength": 10
  },
  "include": ["**/*"],
  "ignore": {
    "useGitignore": true,
    "useDefaultPatterns": true,
    "customPatterns": [
      "**/node_modules/**",
      "**/.git/**",
      "**/dist/**",
      "**/.venv/**",
      "**/*.sqlite*",
      "**/*.db",
      "**/*.png",
      "**/*.jpg",
      "**/*.blend*",
      "repomix-output.*"
    ]
  },
  "security": {
    "enableSecurityCheck": true
  }
}
```

---

## 4. Integration with Cherry Studio

1. Run `python scripts/repomix_pack.py "D:/Projects/<Repo>" --copy`.
2. Open **Cherry Studio**.
3. Select any **Sektor9** model (e.g. `sektor9-autorouter` or `sektor9-code`).
4. Paste the clipboard contents and ask your prompt:
   > *"Analyze this repository architecture and suggest improvements for database caching."*
