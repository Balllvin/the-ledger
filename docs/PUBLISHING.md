# Publishing

Use this workflow to publish a clean public repository without private local usage records.

## Local Branch

If this folder is not already a git repository:

```bash
git init
git checkout -b public-template
```

If it is already a git repository:

```bash
git checkout -b public-template
```

## Privacy Check

Before staging:

```bash
git status --short
python -m unittest discover -s tests
```

Do not stage:

- `.codex/`
- `sessions/`
- `archived_sessions/`
- `state_*.sqlite`
- `logs_*.sqlite`
- `auth.json`
- `*.jsonl`
- `*.log`
- `__pycache__/`
- screenshots containing real usage
- exported local app data

Run a final text search for user-specific paths:

```bash
git grep -n "C:\\\\Users\\|/Users/|/home/" -- .
```

Path examples in documentation are allowed only when they are generic placeholders.

## Commit

```bash
git add .
git status --short
git commit -m "Create The Ledger"
```

## Create GitHub Repository

Creating the remote repository changes a GitHub account and should be confirmed by the user first.

After confirmation:

```bash
gh repo create the-ledger --public --source . --remote origin --push
```

Use `--private` instead of `--public` if the user asks for a private repo.

## After Publishing

Open the GitHub repo page and confirm:

- README renders.
- No local usage files appear.
- AGENTS.md links resolve.
- Tests and source files are present.
