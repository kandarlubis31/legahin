# legahin

A CLI that finds the storage you are actually wasting, then gets an LLM to suggest what is
safe to delete. It reports; it does not delete anything on its own.

## Why

`du -sh` tells you a folder is big. It does not tell you which of those bytes are duplicate
copies of the same video, which are untouched since 2024, and which are build artefacts you can
regenerate in ten seconds. legahin answers that.

## What it does

- Walks a directory tree and skips the noise: `.git`, `node_modules`, `__pycache__`, virtual
  environments, `dist`, `build`, `.cache`, and system folders.
- Flags **large files** (over 50 MB by default).
- Flags **stale files** — untouched for more than 180 days.
- Finds **duplicates** by hashing file contents (MD5, streamed in 64 KB chunks) rather than by
  name or size, so renamed copies still show up.
- Reports free-space pressure when the volume drops below 20 % free.
- Sends the findings to an LLM through **OpenRouter** and asks it to rank what is worth deleting
  and why.

## Requirements

- Python 3.9+
- `openai` (used as the OpenRouter client)
- An OpenRouter API key

## Setup

```bash
pip install openai
export OPENROUTER_API_KEY='sk-or-...'
```

## Run

```bash
python cleaner.py <path>
```

Optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | Required. OpenRouter key |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Any OpenRouter model id |

Thresholds live at the top of `cleaner.py` as constants (`LARGE_FILE_MB`, `OLD_FILE_DAYS`,
`MIN_FREE_PERCENT`).

## Safety

The tool is read-only. It computes hashes and prints a report; deletion is your decision. Even
duplicate detection only identifies candidates — verify before removing anything, especially if
the files are part of a backup set.

Hashing every file can take a while on a large drive, and MD5 is used purely for speed of
comparison, not for integrity guarantees.

## License

MIT
