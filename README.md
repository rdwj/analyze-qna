# analyze-qna

CLI to analyze Q&A YAML files and report token counts and structure quality.

## Features
- **Token counting**: Uses `tiktoken` (OpenAI) by default; optional Mistral tokenizer.
- **Structure checks**: Validates presence of `seed_examples`, 5–15 examples, 3 Q&A pairs per example.
- **Thresholds**: Flags context token counts outside 300–500 and section totals over 750.
- **Directory crawl**: `--taxonomy-root` crawls a tree and analyzes files named `qna.yaml`.
- **Readable report**: Pretty table output via `tabulate` with color highlighting.

## Installation

- Local development:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`

- After publish (or via npm link), use `npx`:
  - `npx analyze-qna --help`

## Usage

- Direct Python
  - `python src/analyze_qna.py --file path/to/qna.yaml`
  - `python src/analyze_qna.py --taxonomy-root path/to/taxonomy`
  - `python src/analyze_qna.py --data-dir path/to/dir` (deprecated)

- Via npx (after publishing or via npm link)
  - `npx analyze-qna --file path/to/qna.yaml`
  - `npx analyze-qna --taxonomy-root path/to/taxonomy`

## Examples

- Analyze single file:
  - `analyze-qna --file ./datasets/foo/qna.yaml`

- Analyze taxonomy tree only for `qna.yaml` files:
  - `analyze-qna --taxonomy-root ./datasets`

## Output

The tool prints a table per file like:

```
Q&A Analysis Report:
+---------+-----------+-----------+-----------+---------+-----------------------------+
|   Index |   C-Tokens|   Q-Tokens|   A-Tokens|   Total | Status                      |
+---------+-----------+-----------+-----------+---------+-----------------------------+
|       1 |       420 |       180 |       210 |     810 | Total Section Tokens: 810   |
|       2 |       310 |       200 |       220 |     730 | OK                          |
+---------+-----------+-----------+-----------+---------+-----------------------------+
```

- Context tokens outside 300–500 are highlighted in yellow.
- Total section tokens > 750 are highlighted in red and flagged.

## Development

- Create and activate a venv, then install requirements:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`

- Run locally via Node wrapper:
  - `node bin/analyze-qna.js --file path/to/qna.yaml`

- Linting/type hints: optional stubs included in `requirements.txt` (`types-PyYAML`, `types-tabulate`).

## Publishing

1. Ensure executable bit on the Node bin
   - `chmod +x bin/analyze-qna.js`
   - `git update-index --chmod=+x bin/analyze-qna.js`
2. Verify package metadata in `package.json`
3. Dry run: `npm pack`, inspect tarball
4. Login & publish: `npm login` then `npm publish` (or `npm publish --access public` for scoped)
5. Post-publish test: `npx analyze-qna --help`

## License

MIT. See `LICENSE` for details.
