# analyze-qna

CLI to analyze InstructLab `qna.yaml` files and report token counts, structure quality, and formatting lint. This tool is intended to help authors ensure their datasets pass InstructLab validations before running `ilab taxonomy diff`.

<p align="center">
  <a href="https://github.com/rdwj/analyze-qna">GitHub Repository</a> ·
  <a href="https://github.com/rdwj/analyze-qna/issues">Issue Tracker</a> ·
  <a href="https://github.com/rdwj/analyze-qna/blob/main/CONTRIBUTING.md">Contributing</a>
</p>

## Features
- **Token counting**: Uses `tiktoken` (OpenAI).
- **Rules enforced**:
  - Context ~500 tokens (default warn if outside 300–500)
  - Each Q/A pair ~250 tokens (default warn if outside 200–300)
  - Context + all pairs ≤ 750 tokens (error if over)
  - Max 3 Q/A pairs (extra pairs ignored; warning emitted)
  - 5–15 sections required (warning otherwise)
  - Optional checks: Q and A text present in context; context appears in source doc (when provided)
- **Configurable thresholds**: via `--config` or CLI flags (see below)
- **Stronger source matching**: normalized substring + line-based fraction matching
- **Directory crawl**: `--taxonomy-root` crawls a tree and analyzes files named `qna.yaml`.
- **Readable report**: Pretty table output via `tabulate` with per-pair breakout.
- **Agent mode**: `--ai` emits structured JSON for programmatic use.
- **YAML lint**: `--yaml-lint` checks trailing whitespace, missing final newline, tabs/mixed indentation, CRLF endings, and duplicate keys.

## Installation

- Local development:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`

- After publish (or via npm link), use `npx`:
  - `npx analyze-qna --help`

## Usage

- Direct Python
  - `python src/analyze_qna.py --file path/to/qna.yaml`
  - `python src/analyze_qna.py --file path/to/qna.yaml --ai`
  - `python src/analyze_qna.py --file path/to/qna.yaml --ai --source-doc path/to/source.txt`
  - `python src/analyze_qna.py --taxonomy-root path/to/taxonomy`
  - `python src/analyze_qna.py --taxonomy-root path/to/taxonomy --ai`
  - `python src/analyze_qna.py --file path/to/qna.yaml --yaml-lint`
  - `python src/analyze_qna.py --taxonomy-root path/to/taxonomy --yaml-lint`
  - `python src/analyze_qna.py --data-dir path/to/dir` (deprecated)

- Via npx (after publishing or via npm link)
  - `npx analyze-qna --file path/to/qna.yaml`
  - `npx analyze-qna --taxonomy-root path/to/taxonomy`
  - `npx analyze-qna --file path/to/qna.yaml --yaml-lint`

## Configuration and thresholds

You can provide a JSON config or override values via CLI.

- JSON file (example `config.json`):
```json
{
  "context_min": 320,
  "context_max": 520,
  "pair_min": 180,
  "pair_max": 320,
  "section_max": 800,
  "examples_min": 5,
  "examples_max": 15,
  "line_match_min_length": 30,
  "line_match_fraction_min": 0.85
}
```

- CLI flags:
  - `--config config.json`
  - `--context-range 320,520`
  - `--pair-range 180,320`
  - `--examples-range 5,15`
  - `--section-max 800`
  - `--line-match-min-length 30`
  - `--line-match-fraction-min 0.85`

## Examples

- Analyze single file:
  - `analyze-qna --file ./datasets/foo/qna.yaml`
- Agent-friendly JSON output:
  - `analyze-qna --file ./datasets/foo/qna.yaml --ai`
- Verify context against original source document:
  - `analyze-qna --file ./datasets/foo/qna.yaml --ai --source-doc ./datasets/foo/source.txt`
- Override thresholds on the fly:
  - `analyze-qna --taxonomy-root ./datasets --context-range 350,550 --pair-range 180,320 --section-max 800`

## Output

Human-readable table per file with per-pair breakout (Q/A tokens, totals, and whether they appear in context). A Notes section lists warnings (extra pairs ignored, out-of-range pairs, missing Q/A in context, context not matching source document).

When `--yaml-lint` is enabled, a YAML Lint section lists any formatting issues (trailing whitespace, missing final newline, CRLF, tabs/mixed indentation, duplicate keys).

## Schema validation (InstructLab v3)

- Validates knowledge QnA files against a bundled InstructLab v3 JSON Schema when the file path contains `/knowledge/` (e.g., when analyzing a taxonomy tree).
- Human mode prints a "Schema Validation" section with the failing path and a short hint from the schema when available.
- AI mode adds a `schema` block in the JSON output with `validated_against` and detailed errors.

Bundled schemas (offline):
- `src/instructlab/schema/v3/knowledge.json`
- Upstream references: InstructLab schemas v3 and taxonomy layout
  - https://github.com/instructlab/schema/tree/main/src/instructlab/schema/v3
  - https://github.com/instructlab/taxonomy

Notes:
- Requires `jsonschema` (already in `requirements.txt`); the Node wrapper installs it automatically.
- If `schema.validated_against` is `null`, validation was skipped (non-knowledge path or schema not found).
- Currently validates knowledge QnA. Other dataset types (e.g., compositional, foundational) receive lint checks; schema validation for those types can be added later.

## Contributing

Contributions are welcome! Please read the guidelines in [`CONTRIBUTING.md`](https://github.com/rdwj/analyze-qna/blob/main/CONTRIBUTING.md) and open an issue or pull request on GitHub.

- Repo: `https://github.com/rdwj/analyze-qna`
- Issues: `https://github.com/rdwj/analyze-qna/issues`
- Maintainer: Wes Jackson (`wjackson@redhat.com`)

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
   - `git add --chmod=+x bin/analyze-qna.js`
2. Bump version and dry run
   - `npm version patch`
   - `FILE=$(npm pack --silent) && echo $FILE && tar -tf $FILE | cat`
3. Login & publish
   - `npm login`
   - `npm publish`
4. Post-publish test
   - `npx analyze-qna --help`

## License

MIT. See `LICENSE` for details.

## Acknowledgement

This utility is designed for use with InstructLab `qna.yaml` datasets and aims to mirror important validations to reduce failures during `ilab taxonomy diff`. InstructLab is an open-source project; please consult its documentation for canonical requirements and behavior.
