# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is `analyze-qna`, a CLI tool that analyzes InstructLab `qna.yaml` files for token counts, structure quality, and formatting issues. It's published as an npm package that wraps a Python script.

## Key Commands

### Development Setup
```bash
# Create and activate Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Tool
```bash
# Direct Python execution (development)
python src/analyze_qna.py --file path/to/qna.yaml
python src/analyze_qna.py --taxonomy-root path/to/taxonomy
python src/analyze_qna.py --file path/to/qna.yaml --ai  # JSON output mode

# Via Node wrapper (simulates npm package behavior)
node bin/analyze-qna.js --file path/to/qna.yaml

# After npm link or publish
npx analyze-qna --help
```

### Publishing
```bash
# Use the publish script (handles version bump, pack, and publish)
scripts/publish.sh [patch|minor|major]

# Or manually:
npm version patch --no-git-tag-version
npm pack
npm publish
```

## Architecture

### Dual Distribution System
The project is distributed as an npm package that contains a Python application:

1. **Node.js wrapper** (`bin/analyze-qna.js`): Entry point when installed via npm
   - Automatically creates a Python venv in `.venv/`
   - Installs Python dependencies from `requirements.txt`
   - Forwards all arguments to the Python script
   - Sets environment variables: `ANALYZE_QNA_ROOT` and `ANALYZE_QNA_VERSION`

2. **Python core** (`src/analyze_qna.py`): Main analysis logic
   - Uses `tiktoken` for OpenAI token counting
   - Validates against InstructLab v3 JSON schemas
   - Two output modes: human-readable tables (default) or structured JSON (`--ai` flag)

### Key Analysis Functions

- **Token Counting**: Uses OpenAI's tiktoken library to count tokens for context and Q/A pairs
- **Validation Rules**: Enforces InstructLab requirements (context ~500 tokens, pairs ~250 tokens, max 750 total)
- **Schema Validation**: When analyzing knowledge files, validates against bundled InstructLab v3 JSON schemas
- **YAML Linting**: Optional checks for formatting issues (trailing whitespace, tabs, CRLF, etc.)
- **Source Matching**: Can verify that context text appears in source documents

### Configuration System

Thresholds can be configured via:
1. JSON config file (`--config config.json`)
2. CLI flags (`--context-range 320,520`, `--pair-range 180,320`)
3. Defaults in `DEFAULT_THRESHOLDS` dictionary

### Schema Files

Bundled InstructLab v3 schemas are stored in `src/instructlab/schema/v3/`:
- `knowledge.json`: Schema for knowledge Q&A files
- `compositional_skills.json`: Schema for compositional skills
- `version.json`: Version information

These are automatically loaded when validating files in `/knowledge/` paths.