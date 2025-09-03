# InstructLab QnA Analyzer - AI Assistant Guide

## Overview

I have a tool called `analyze-qna` that validates InstructLab QnA YAML files. It checks token counts, validates structure, enforces InstructLab schema requirements, and helps ensure datasets will pass `ilab taxonomy diff` validation.

## Installation & Basic Usage

```bash
# Install globally via npm
npm install -g analyze-qna

# Run on a single file
npx analyze-qna --file path/to/qna.yaml

# Run on entire taxonomy tree
npx analyze-qna --taxonomy-root path/to/taxonomy

# Get AI-friendly JSON output
npx analyze-qna --file path/to/qna.yaml --ai
```

## Key Features

1. **Token Counting**: Uses OpenAI's tiktoken to count tokens
2. **Schema Validation**: Validates against InstructLab v3 JSON schemas for knowledge files
3. **Structure Checks**: Ensures proper Q&A format and content requirements
4. **YAML Linting**: Optional formatting checks with `--yaml-lint`

## Understanding the Rules

### Token Requirements
- **Context**: Should be ~500 tokens (warns if outside 300-500 range)
- **Each Q/A pair**: Should be ~250 tokens (warns if outside 200-300 range)
- **Total per section**: Must not exceed 750 tokens (hard limit)
- **Q/A pairs per section**: Maximum 3 (extras are ignored with warning)

### Structure Requirements
- **Seed examples**: 5-15 required (warns outside this range)
- **Knowledge files** must have:
  - `version: 3`
  - `created_by`: GitHub username
  - `domain`: Knowledge domain
  - `seed_examples`: Array of examples
  - `document`: Source document info
  - `document_outline`: Document structure

## Example: Valid Knowledge File

Here's a properly structured knowledge file that passes all validations:

```yaml
version: 3
created_by: documentation_example
domain: Python Programming
seed_examples:
  - context: |
      Python is a high-level, interpreted programming language known for its 
      simplicity and readability. It was created by Guido van Rossum and first 
      released in 1991. Python's design philosophy emphasizes code readability 
      with the use of significant indentation.
    questions_and_answers:
      - question: Who created the Python programming language?
        answer: Guido van Rossum created the Python programming language.
      - question: When was Python first released?
        answer: Python was first released in 1991.
      - question: What does Python's design philosophy emphasize?
        answer: |
          Python's design philosophy emphasizes code readability with the use 
          of significant indentation.
  # ... 4 more seed_examples (minimum 5 total) ...
document:
  repo: https://github.com/python/docs
  commit: abc123def456
  patterns:
    - docs/tutorial/introduction.md
document_outline: |
  # Python Programming Language
  ## Introduction and History
  ## Language Features
```

### AI Output for Valid File

When you run with `--ai` flag, you get structured JSON:

```json
{
  "file": "examples/knowledge/valid/qna.yaml",
  "ok": false,  // false if ANY constraint fails
  "errors": [],
  "seed_examples_count": 5,
  "constraints": {
    "num_examples_recommended": {
      "min": 5,
      "max": 15,
      "ok": true
    }
  },
  "examples": [
    {
      "index": 1,
      "context_tokens": 50,
      "question_tokens_total": 21,
      "answer_tokens_total": 35,
      "total_section_tokens": 106,
      "constraints": {
        "context_tokens_range_ok": false,  // Too few tokens (50 < 300)
        "qna_pairs_count_ok": true,
        "total_section_tokens_max_ok": true,
        "context_deviation_from_500": 450,
        "pairs_ignored": 0
      },
      "pairs": [
        {
          "pair_index": 1,
          "question_tokens": 7,
          "answer_tokens": 11,
          "pair_tokens_total": 18,
          "constraints": {
            "pair_tokens_recommended_ok": false,  // Too few (18 < 200)
            "question_in_context": false,
            "answer_in_context": false,
            "context_in_source": null,
            "pair_words_total": 14
          }
        }
        // ... more pairs ...
      ]
    }
    // ... more examples ...
  ],
  "schema": {
    "validated_against": "v3/knowledge.json",
    "source": "package",
    "errors": []  // Empty = schema valid
  }
}
```

## Common Validation Failures

### 1. Missing Version Field

```yaml
# INVALID: Missing version field
created_by: test_user
domain: Testing
seed_examples: [...]
```

**AI Output Shows:**
```json
{
  "schema": {
    "validated_against": "v3/knowledge.json",
    "errors": [
      {
        "path": "<root>",
        "message": "'version' is a required property"
      }
    ]
  }
}
```

### 2. Too Few Seed Examples

```yaml
version: 3
created_by: test_user
domain: Testing
seed_examples:  # Only 2 examples instead of minimum 5
  - context: "..."
    questions_and_answers: [...]
  - context: "..."
    questions_and_answers: [...]
```

**AI Output Shows:**
```json
{
  "ok": false,
  "errors": [
    "Expected 5-15 seed examples, found 2"
  ],
  "seed_examples_count": 2,
  "constraints": {
    "num_examples_recommended": {
      "min": 5,
      "max": 15,
      "ok": false  // Failed constraint
    }
  }
}
```

### 3. Missing Required Fields

```yaml
version: 3
created_by: test_user
domain: Testing
seed_examples: [...]
# MISSING: document and document_outline
```

**AI Output Shows:**
```json
{
  "schema": {
    "errors": [
      {
        "path": "<root>",
        "message": "'document_outline' is a required property"
      }
    ]
  }
}
```

## Best Practices for Using the Analyzer

### 1. Check Token Counts
When the analyzer reports token issues, look for:
- **Context too short**: Add more relevant information
- **Context too long**: Split into multiple seed examples
- **Q/A pairs too short**: Make questions/answers more detailed
- **Total exceeds 750**: Reduce content or split sections

### 2. Ensure Q&A Quality
The analyzer checks if questions and answers appear in context:
```json
{
  "constraints": {
    "question_in_context": false,  // Question text not found in context
    "answer_in_context": true       // Answer text found in context
  }
}
```

### 3. Schema Validation for Knowledge Files
Only files in `/knowledge/` paths get schema validation. Files elsewhere get basic QnA checks.

### 4. Use --ai Flag for Automation
The `--ai` flag provides structured JSON perfect for:
- CI/CD pipelines
- Automated validation scripts
- Batch processing multiple files
- Integration with other tools

## Interpreting Results

### Understanding "ok" Field
- `"ok": true` - All constraints pass
- `"ok": false` - At least one constraint failed (check individual constraints)

### Token Deviation
`"context_deviation_from_500": 450` means the context is 450 tokens away from the ideal 500.

### Pairs Ignored
`"pairs_ignored": 1` means you had 4+ Q/A pairs, and the extras were ignored.

## Advanced Usage

### Custom Thresholds
```bash
# Override token ranges
npx analyze-qna --file qna.yaml --context-range 320,520 --pair-range 180,320

# Use config file
npx analyze-qna --file qna.yaml --config custom_config.json
```

### Config File Example
```json
{
  "context_min": 320,
  "context_max": 520,
  "pair_min": 180,
  "pair_max": 320,
  "section_max": 800,
  "examples_min": 5,
  "examples_max": 15
}
```

### YAML Linting
```bash
npx analyze-qna --file qna.yaml --yaml-lint
```

Checks for:
- Trailing whitespace
- Missing final newline
- CRLF line endings
- Mixed indentation (tabs/spaces)
- Duplicate keys

## Troubleshooting

### "Schema validation skipped"
- File is not in a `/knowledge/` path
- Schema files couldn't be loaded (rare)

### "Q or A not fully present in context"
- The exact question/answer text isn't found in the context
- This is a warning, not an error
- Consider rephrasing to use words from the context

### Token counts seem wrong
- The tool uses OpenAI's tiktoken library
- Different models may tokenize differently
- The defaults target GPT-3.5/4 tokenization

## Summary for AI Agents

When using this tool programmatically:

1. **Always use `--ai` flag** for JSON output
2. **Check `"ok"` field** for overall pass/fail
3. **Examine `"errors"` array** for critical issues
4. **Review `"schema.errors"` ** for validation failures
5. **Inspect individual constraints** for specific issues
6. **Token counts** are in the examples[].pairs[] structures
7. **Schema validation** only applies to `/knowledge/` paths

The tool helps ensure InstructLab QnA files are properly formatted, have appropriate token counts, and will successfully validate with `ilab taxonomy diff`.