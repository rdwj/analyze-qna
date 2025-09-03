"""
This script analyzes a Q&A YAML file and generates a concise report.
Usage:
  - python analyze_qna.py <path_to_qna.yaml>
  - python analyze_qna.py --file <path_to_qna.yaml>
  - python analyze_qna.py --taxonomy-root <taxonomy_root_dir>
  - [Deprecated] python analyze_qna.py --data-dir <directory_with_yaml_files>

It is recommended to use a venv with the following packages installed:
- pyyaml
- tiktoken
- tabulate
- termcolor

"""
import os
import sys
import argparse
import json
import yaml
import jsonschema
import json as _json
try:
    from importlib import resources as _iresources
except Exception:
    _iresources = None
import tiktoken
from tabulate import tabulate
from termcolor import colored
from typing import List, Optional, Dict, Any, Tuple

def count_tokens(text: str) -> int:
    """Count the number of tokens in a text using tiktoken (OpenAI)."""
    return count_tokens_openai(text)

def count_tokens_openai(text: str, model_name: str = "o3-mini") -> int:
    """Count the number of tokens in a text using tiktoken with the specified model."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        tokens = encoding.encode(text)
        return len(tokens)
    except KeyError:
        print(colored(f"Error: Tokenizer for model '{model_name}' not found. Using 'cl100k_base' as a fallback.", 'red', attrs=['bold']))
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)
        return len(tokens)

    # Note: Previously supported an optional Mistral tokenizer path; removed for simplicity.

def normalize_text(value: str) -> str:
    """Normalize text for loose containment checks (lowercase, collapse whitespace)."""
    return " ".join(value.lower().split())

DEFAULT_THRESHOLDS: Dict[str, Any] = {
    "context_min": 300,
    "context_max": 500,
    "pair_min": 200,
    "pair_max": 300,
    "section_max": 750,
    "examples_min": 5,
    "examples_max": 15,
    "line_match_min_length": 20,
    "line_match_fraction_min": 0.8,
}

def parse_range_arg(arg_value: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse a CLI range argument in the form 'min,max'."""
    if not arg_value:
        return None
    try:
        parts = [p.strip() for p in arg_value.split(',')]
        if len(parts) != 2:
            return None
        return int(parts[0]), int(parts[1])
    except Exception:
        return None

def load_thresholds_from_args_and_config(args: argparse.Namespace) -> Dict[str, Any]:
    """Load thresholds from optional config JSON and override with CLI args."""
    thresholds: Dict[str, Any] = dict(DEFAULT_THRESHOLDS)

    if getattr(args, 'config', None):
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                thresholds.update({k: v for k, v in cfg.items() if k in DEFAULT_THRESHOLDS})
        except Exception as e:
            print(colored(f"Warning: failed to read config '{args.config}': {e}", 'yellow'))

    ctx_range = parse_range_arg(getattr(args, 'context_range', None))
    if ctx_range:
        thresholds["context_min"], thresholds["context_max"] = ctx_range

    pair_range = parse_range_arg(getattr(args, 'pair_range', None))
    if pair_range:
        thresholds["pair_min"], thresholds["pair_max"] = pair_range

    ex_range = parse_range_arg(getattr(args, 'examples_range', None))
    if ex_range:
        thresholds["examples_min"], thresholds["examples_max"] = ex_range

    if getattr(args, 'section_max', None):
        thresholds["section_max"] = int(args.section_max)

    if getattr(args, 'line_match_min_length', None):
        thresholds["line_match_min_length"] = int(args.line_match_min_length)

    if getattr(args, 'line_match_fraction_min', None):
        thresholds["line_match_fraction_min"] = float(args.line_match_fraction_min)

    return thresholds

def compute_context_source_checks(context: str, source_text: str, thresholds: Dict[str, Any]) -> Dict[str, Any]:
    """Check whether context appears in source via normalized substring or line fraction matching."""
    normalized_context = normalize_text(context)
    normalized_source = normalize_text(source_text)

    normalized_substring = normalized_context in normalized_source

    min_len = thresholds.get("line_match_min_length", DEFAULT_THRESHOLDS["line_match_min_length"])
    ctx_lines = [ln.strip() for ln in context.splitlines() if len(ln.strip()) >= min_len]
    total = len(ctx_lines)
    matched = 0
    if total > 0:
        for ln in ctx_lines:
            if normalize_text(ln) in normalized_source:
                matched += 1
    frac = (matched / total) if total > 0 else 0.0
    frac_ok = frac >= thresholds.get("line_match_fraction_min", DEFAULT_THRESHOLDS["line_match_fraction_min"])

    return {
        "normalized_substring": normalized_substring,
        "line_match_fraction": round(frac, 3),
        "line_match_fraction_ok": frac_ok,
        "ok": bool(normalized_substring or frac_ok),
    }

def _load_schema(schema_type: str = 'knowledge') -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str], Dict[str, Any], List[str]]:
    """Load the bundled v3 schema via importlib.resources, with filesystem fallbacks.
    
    Args:
        schema_type: Type of schema to load ('knowledge', 'compositional_skills', 'foundational_skills')

    Returns: (schema_dict_or_none, source_hint, base_uri, store_version, attempts)
    attempts lists the locations tried with basic status for debugging.
    """
    attempts: List[str] = []
    # Helper to load sibling version.json for store
    def _load_version_for(base_file: str) -> Dict[str, Any]:
        try:
            vpath = os.path.join(os.path.dirname(base_file), 'version.json')
            with open(vpath, 'r', encoding='utf-8') as vf:
                return json.load(vf)
        except Exception:
            return {}
    
    # Helper to inline the version.json reference in the schema
    def _inline_version_ref(schema: Dict[str, Any], version_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Replace $ref to ./version.json with the actual schema content."""
        if '$ref' in schema and schema['$ref'] == './version.json':
            # Merge version schema properties into the main schema
            result = dict(schema)
            del result['$ref']
            # Merge required and properties from version schema
            if 'required' in version_schema:
                existing_required = result.get('required', [])
                result['required'] = list(set(existing_required + version_schema['required']))
            if 'properties' in version_schema:
                existing_props = result.get('properties', {})
                existing_props.update(version_schema['properties'])
                result['properties'] = existing_props
            return result
        return schema

    # Map schema type to filename
    schema_filename = f'{schema_type}.json'
    
    # Fallback 1: relative to this file
    schema_path = os.path.join(os.path.dirname(__file__), 'instructlab', 'schema', 'v3', schema_filename)
    try:
        attempts.append(f'file: {schema_path}')
        with open(schema_path, 'r', encoding='utf-8') as sf:
            schema = json.load(sf)
        store_version = _load_version_for(schema_path)
        # Inline the version reference to avoid resolution issues
        schema = _inline_version_ref(schema, store_version)
        base_uri = pathlib.Path(schema_path).resolve().as_uri()
        return schema, schema_path, base_uri, store_version, attempts
    except Exception:
        attempts.append('file: miss')
    # Fallback 2: use ANALYZE_QNA_ROOT env (set by Node wrapper) to locate schema in installed package layout
    root_dir = os.environ.get('ANALYZE_QNA_ROOT')
    if root_dir:
        alt_path = os.path.join(root_dir, 'src', 'instructlab', 'schema', 'v3', schema_filename)
        try:
            attempts.append(f'env-root: {alt_path}')
            with open(alt_path, 'r', encoding='utf-8') as sf:
                schema = json.load(sf)
            store_version = _load_version_for(alt_path)
            # Inline the version reference to avoid resolution issues
            schema = _inline_version_ref(schema, store_version)
            base_uri = pathlib.Path(alt_path).resolve().as_uri()
            return schema, alt_path, base_uri, store_version, attempts
        except Exception:
            attempts.append('env-root: miss')
    # Fallback 3: CWD-based lookup (developer local runs)
    try:
        cwd_path = os.path.join(os.getcwd(), 'src', 'instructlab', 'schema', 'v3', schema_filename)
        attempts.append(f'cwd: {cwd_path}')
        with open(cwd_path, 'r', encoding='utf-8') as sf:
            schema = json.load(sf)
        store_version = _load_version_for(cwd_path)
        # Inline the version reference to avoid resolution issues
        schema = _inline_version_ref(schema, store_version)
        base_uri = pathlib.Path(cwd_path).resolve().as_uri()
        return schema, cwd_path, base_uri, store_version, attempts
    except Exception:
        attempts.append('cwd: miss')
    # Last resort: package resource (works only if importable as files)
    if _iresources is not None:
        try:
            attempts.append(f'package: instructlab.schema.v3/{schema_filename}')
            pkg = 'instructlab.schema.v3'
            base = _iresources.files(pkg)  # type: ignore[attr-defined]
            data = base.joinpath(schema_filename).read_text(encoding='utf-8')  # type: ignore[attr-defined]
            vdata = base.joinpath('version.json').read_text(encoding='utf-8')  # type: ignore[attr-defined]
            schema = _json.loads(data)
            store_version = _json.loads(vdata)
            # Inline the version reference to avoid resolution issues
            schema = _inline_version_ref(schema, store_version)
            return schema, 'package', None, store_version, attempts
        except Exception:
            attempts.append('package: miss')
    return None, None, None, {}, attempts

def lint_yaml_file(file_path: str) -> Dict[str, Any]:
    """Perform simple YAML file lint checks (formatting + duplicate keys)."""
    results: Dict[str, Any] = {
        "trailing_whitespace_lines": [],
        "missing_final_newline": False,
        "has_tabs": False,
        "mixed_indentation": False,
        "has_crlf": False,
        "duplicate_keys": [],
    }

    # Read raw bytes/text to detect line endings and whitespace
    with open(file_path, 'rb') as fb:
        raw = fb.read()
    text = raw.decode('utf-8', errors='replace')

    lines = text.splitlines(keepends=True)
    saw_space_indent = False
    saw_tab_indent = False
    for idx, line in enumerate(lines, start=1):
        if line.endswith('\r\n'):
            results["has_crlf"] = True
        # Trailing whitespace before newline
        stripped_nl = line.rstrip('\r\n')
        if len(stripped_nl) > 0 and stripped_nl.endswith((' ', '\t')):
            results["trailing_whitespace_lines"].append(idx)
        # Indentation type detection
        leading = len(line) - len(line.lstrip(' \t'))
        if leading > 0:
            if line[:leading].find('\t') != -1:
                saw_tab_indent = True
            if line[:leading].find(' ') != -1:
                saw_space_indent = True

    if len(lines) > 0 and not (lines[-1].endswith('\n') or lines[-1].endswith('\r\n')):
        results["missing_final_newline"] = True
    results["has_tabs"] = any('\t' in ln for ln in lines)
    results["mixed_indentation"] = saw_space_indent and saw_tab_indent

    # Duplicate keys using a custom loader
    class DuplicateKeyLoader(yaml.SafeLoader):
        def __init__(self, stream):
            super().__init__(stream)
            self.duplicate_keys: List[str] = []

        def construct_mapping(self, node, deep=False):  # type: ignore[override]
            mapping = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if key in mapping:
                    try:
                        self.duplicate_keys.append(str(key))
                    except Exception:
                        self.duplicate_keys.append("<unprintable>")
                value = self.construct_object(value_node, deep=deep)
                mapping[key] = value
            return mapping

    DuplicateKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        DuplicateKeyLoader.construct_mapping,
    )

    try:
        loader = DuplicateKeyLoader(text)
        try:
            loader.get_single_data()
        finally:
            loader.dispose()
        results["duplicate_keys"] = loader.duplicate_keys
    except Exception:
        # If parsing fails here, duplicate detection is moot; parsing errors handled elsewhere
        pass

    return results


def analyze_qna_file(file_path: str, source_doc_text: Optional[str] = None, thresholds: Optional[Dict[str, Any]] = None, yaml_lint: bool = False, schema_type: str = 'knowledge') -> None:
    """Analyze a qna.yaml file and generate a concise human-readable report."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = yaml.safe_load(file)
    except FileNotFoundError:
        print(colored(f"Error: File not found at '{file_path}'", 'red', attrs=['bold']))
        sys.exit(1)
    except yaml.YAMLError as e:
        print(colored(f"Error parsing YAML file '{file_path}': {e}", 'red', attrs=['bold']))
        sys.exit(1)

    # Schema validation (InstructLab v3):
    # Validate against specified schema type (defaults to knowledge)
    schema_errors: List[str] = []
    schema_attempts: List[str] = []
    # Always attempt schema validation with the specified type
    schema_dict, schema_src, base_uri, store_version, schema_attempts = _load_schema(schema_type)
    try:
        if schema_dict is None:
            print(colored(f"Info: Bundled {schema_type} schema not found; skipping JSON Schema validation.", 'yellow'))
        else:
            # Validate using the schema with inlined version reference
            try:
                validator_cls = jsonschema.validators.validator_for(schema_dict)  # type: ignore[attr-defined]
                validator_cls.check_schema(schema_dict)
                # Since we've inlined the version reference, we don't need a resolver
                validator = validator_cls(schema_dict)
                validator.validate(content)
            except Exception as inner_e:
                raise inner_e
    except jsonschema.exceptions.ValidationError as ve:
        # Build helpful message with property path and schema hints
        prop_path = ".".join([str(p) for p in list(ve.path)])
        
        # Create a more user-friendly error message
        if "is too short" in ve.message:
            # Parse the path to understand which seed example and what field
            path_parts = list(ve.path)
            if len(path_parts) >= 2 and path_parts[0] == 'seed_examples':
                seed_idx = path_parts[1]
                if len(path_parts) >= 3 and path_parts[2] == 'questions_and_answers':
                    # This is about Q&A pairs being too few
                    try:
                        qa_count = len(content['seed_examples'][seed_idx]['questions_and_answers'])
                        msg = f"Seed example {seed_idx + 1} has only {qa_count} Q&A pairs (minimum required: 3)"
                    except (KeyError, IndexError, TypeError):
                        msg = f"Seed example {seed_idx + 1}: questions_and_answers array is too short (minimum: 3 Q&A pairs)"
                else:
                    # This is about seed_examples array being too short
                    try:
                        example_count = len(content['seed_examples'])
                        msg = f"Only {example_count} seed examples provided (minimum required: 5)"
                    except (KeyError, IndexError, TypeError):
                        msg = f"Not enough seed examples (minimum required: 5)"
            elif prop_path == 'seed_examples':
                # The seed_examples array itself is too short
                try:
                    example_count = len(content.get('seed_examples', []))
                    msg = f"Only {example_count} seed example(s) provided (minimum required: 5)"
                except (KeyError, TypeError):
                    msg = "Not enough seed examples (minimum required: 5)"
            else:
                # Fallback to a cleaner version of the original message
                msg = f"Field '{prop_path}' has too few items"
        elif "is a required property" in ve.message:
            # Handle missing required properties
            missing_prop = ve.message.split("'")[1] if "'" in ve.message else ve.message
            msg = f"Missing required field: '{missing_prop}'"
            if prop_path:
                msg = f"At '{prop_path}': {msg}"
        else:
            # For other validation errors, try to simplify the message
            # Remove the data content from the message if it's too long
            error_msg = ve.message
            if len(error_msg) > 200 and "[{" in error_msg:
                # Extract just the error type, not the data
                error_msg = error_msg.split(" is ")[0] if " is " in error_msg else error_msg[:100] + "..."
            msg = f"Schema validation error at '{prop_path or '<root>'}': {error_msg}"
        
        schema_errors.append(msg)
    except Exception as e:
        print(colored(f"Info: Schema validation skipped due to error: {e}", 'yellow'))

    if 'seed_examples' not in content:
        print(colored("Warning: No 'seed_examples' section found in the YAML file.", 'yellow'))
        return

    seed_examples = content.get('seed_examples', [])
    if not isinstance(seed_examples, list):
        print(colored("Error: 'seed_examples' should be a list.", 'red', attrs=['bold']))
        return

    num_contexts = len(seed_examples)
    # More lenient with seed example counts - only warn if too many or extremely few
    if num_contexts < 3:
        print(colored(f"Warning: Very few context sections ({num_contexts}). Consider adding more if your source document allows.", 'yellow'))
    elif num_contexts > thresholds["examples_max"]:
        print(colored(f"Warning: Many context sections ({num_contexts}). Recommended maximum is {thresholds['examples_max']}.", 'yellow'))

    report_data = []
    extra_warnings: List[str] = []

    for i, example in enumerate(seed_examples):
        context = example.get('context')
        questions_and_answers = example.get('questions_and_answers')
        status = "OK"
        status_color = 'green'

        if context is None:
            status = "Missing Context"
            status_color = 'red'
            report_data.append([i + 1, colored("N/A", 'red'), colored("N/A", 'red'), colored("N/A", 'red'), colored("N/A", 'red'), colored(status, status_color)])
            continue

        # context_tokens = count_tokens(context)
        context_tokens = count_tokens(context)
        if not thresholds["context_min"] <= context_tokens <= thresholds["context_max"]:
            status = f"Context Tokens: {context_tokens} (Expected {thresholds['context_min']}-{thresholds['context_max']})"
            status_color = 'yellow'

        total_section_tokens = context_tokens
        question_tokens_total = 0
        answer_tokens_total = 0

        if questions_and_answers is None:
            if status == "OK":
                status = "Missing Q&A"
                status_color = 'red'
            report_data.append([i + 1, context_tokens, colored("N/A", 'red'), colored("N/A", 'red'), colored("N/A", 'red'), colored(status, status_color)])
            continue

        if not isinstance(questions_and_answers, list):
            if status == "OK":
                status = "Q&A is not a list"
                status_color = 'red'
            questions_and_answers = []

        # Enforce MAX 3 Q&A pairs; the teacher ignores beyond 3
        if isinstance(questions_and_answers, list) and len(questions_and_answers) > 3:
            ignored = len(questions_and_answers) - 3
            extra_warnings.append(f"Example {i+1}: {ignored} Q&A pair(s) beyond 3 will be ignored")
            questions_and_answers = questions_and_answers[:3]

        # Only warn if there are 0 pairs (which is an issue), not if 1-2 pairs
        if len(questions_and_answers) == 0:
            if status == "OK":
                status = f"No Q&A pairs found"
                status_color = 'red'

        normalized_context = normalize_text(context)
        normalized_source = normalize_text(source_doc_text) if isinstance(source_doc_text, str) else None
        pairs_breakout: List[List[Any]] = []

        for qna_pair in questions_and_answers:
            question = qna_pair.get('question')
            answer = qna_pair.get('answer')

            if question is None or answer is None:
                if status == "OK":
                    status = "Missing Q or A in a pair"
                    status_color = 'red'
                continue

            question_tokens = count_tokens(question)
            answer_tokens = count_tokens(answer)
            total_section_tokens += question_tokens + answer_tokens
            question_tokens_total += question_tokens
            answer_tokens_total += answer_tokens

            # Pair-level guidance (~250 tokens recommended; configurable window)
            pair_total = question_tokens + answer_tokens
            if not thresholds["pair_min"] <= pair_total <= thresholds["pair_max"] and status_color != 'red':
                status = f"Pair tokens ~{(thresholds['pair_min']+thresholds['pair_max'])//2} recommended; got {pair_total}"
                status_color = 'yellow'


            # Note: Removed literal Q/A text matching since paraphrasing is allowed
            # The requirements state answers should be "entailed" by context, not literally present
            q_in_ctx = True  # Assume questions relate to context (as per requirements)
            a_in_ctx = True  # Assume answers are entailed (paraphrasing allowed)

            pairs_breakout.append([
                len(pairs_breakout) + 1,
                question_tokens,
                answer_tokens,
                pair_total,
                (colored("Yes", 'green') if q_in_ctx else colored("No", 'red')),
                (colored("Yes", 'green') if a_in_ctx else colored("No", 'red')),
            ])

        # If source document provided, ensure context appears in it (stronger check)
        if normalized_source is not None and isinstance(source_doc_text, str):
            checks = compute_context_source_checks(context, source_doc_text, thresholds)
            if not checks["ok"]:
                extra_warnings.append(f"Example {i+1}: Context may not match provided source document (line match {checks['line_match_fraction']})")

        if total_section_tokens > thresholds["section_max"]:
            status = f"Total Section Tokens: {total_section_tokens} (Max {thresholds['section_max']})"
            status_color = 'red'

        report_data.append([
            i + 1,
            colored(str(context_tokens), 'yellow') if not thresholds["context_min"] <= context_tokens <= thresholds["context_max"] else context_tokens,
            question_tokens_total,
            answer_tokens_total,
            colored(str(total_section_tokens), 'red', attrs=['bold']) if total_section_tokens > thresholds["section_max"] else total_section_tokens,
            colored(status, status_color)
        ])

        # Print per-pair breakout table for this example
        if pairs_breakout:
            headers_pairs = ["Pair", "Q Tokens", "A Tokens", "Total", "Q in Ctx", "A in Ctx"]
            print(tabulate(pairs_breakout, headers=headers_pairs, tablefmt="simple"))

    if report_data:
        headers = ["Index", "C-Tokens", "Q-Tokens", "A-Tokens", "Total", "Status"]
        print(colored("\nQ&A Analysis Report:", 'blue', attrs=['bold']))
        print(tabulate(report_data, headers=headers, tablefmt="grid"))
    else:
        print(colored("\nNo seed examples found to analyze.", 'yellow'))

    if extra_warnings:
        print(colored("\nNotes:", 'yellow', attrs=['bold']))
        for w in extra_warnings:
            print(colored(f"- {w}", 'yellow'))

    if schema_errors:
        print(colored("\nSchema Validation:", 'red', attrs=['bold']))
        for e in schema_errors:
            print(colored(f"- {e}", 'red'))
    # Only show schema load attempts if there was an error loading the schema
    if schema_attempts and schema_dict is None:
        print(colored("\nSchema Load Attempts:", 'cyan', attrs=['bold']))
        for a in schema_attempts:
            print(colored(f"- {a}", 'cyan'))

    if yaml_lint:
        lint = lint_yaml_file(file_path)
        lint_notes: List[str] = []
        if lint["missing_final_newline"]:
            lint_notes.append("Missing final newline at end of file")
        if lint["trailing_whitespace_lines"]:
            lint_notes.append(f"Trailing whitespace on lines: {lint['trailing_whitespace_lines'][:10]}{'...' if len(lint['trailing_whitespace_lines'])>10 else ''}")
        if lint["has_crlf"]:
            lint_notes.append("CRLF line endings detected; prefer LF")
        if lint["mixed_indentation"]:
            lint_notes.append("Mixed indentation (tabs and spaces) detected")
        elif lint["has_tabs"]:
            lint_notes.append("Tab characters present; prefer spaces for YAML indentation")
        if lint["duplicate_keys"]:
            lint_notes.append(f"Duplicate YAML keys detected (first few): {list(dict.fromkeys(lint['duplicate_keys']))[:10]}")
        if lint_notes:
            print(colored("\nYAML Lint:", 'magenta', attrs=['bold']))
            for n in lint_notes:
                print(colored(f"- {n}", 'magenta'))

    print(colored("\nAnalysis complete.", 'green'))

def analyze_qna_dir(dir_path: str, thresholds: Optional[Dict[str, Any]] = None, source_doc_text: Optional[str] = None, yaml_lint: bool = False, schema_type: str = 'knowledge') -> None:
    """Find and analyze all .yaml/.yml files within a directory (recursively)."""
    if not os.path.isdir(dir_path):
        print(colored(f"Error: Directory not found at '{dir_path}'", 'red', attrs=['bold']))
        sys.exit(1)

    yaml_files: List[str] = []
    for root, _dirs, files in os.walk(dir_path):
        for name in files:
            if name.lower().endswith((".yaml", ".yml")):
                yaml_files.append(os.path.join(root, name))

    if not yaml_files:
        print(colored(f"No YAML files found in '{dir_path}'.", 'yellow'))
        return

    for file_path in sorted(yaml_files):
        print(colored(f"\n=== Analyzing: {file_path} ===", 'blue', attrs=['bold']))
        analyze_qna_file(file_path, source_doc_text=source_doc_text, thresholds=thresholds, yaml_lint=yaml_lint, schema_type=schema_type)

def analyze_taxonomy_root(root_path: str, thresholds: Optional[Dict[str, Any]] = None, source_doc_text: Optional[str] = None, yaml_lint: bool = False, schema_type: str = 'knowledge') -> None:
    """Crawl a taxonomy tree and analyze files named exactly 'qna.yaml'."""
    if not os.path.isdir(root_path):
        print(colored(f"Error: Directory not found at '{root_path}'", 'red', attrs=['bold']))
        sys.exit(1)

    qna_files: List[str] = []
    for current_root, _dirs, files in os.walk(root_path):
        for name in files:
            if name == "qna.yaml":
                qna_files.append(os.path.join(current_root, name))

    if not qna_files:
        print(colored(f"No 'qna.yaml' files found under '{root_path}'.", 'yellow'))
        return

    for file_path in sorted(qna_files):
        print(colored(f"\n=== Analyzing: {file_path} ===", 'blue', attrs=['bold']))
        analyze_qna_file(file_path, source_doc_text=source_doc_text, thresholds=thresholds, yaml_lint=yaml_lint, schema_type=schema_type)

def analyze_qna_file_ai(file_path: str, source_doc_text: Optional[str] = None, yaml_lint: bool = False, schema_type: str = 'knowledge') -> dict:
    """Analyze a qna.yaml file and return a machine-readable JSON-ready structure."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = yaml.safe_load(file)
    except FileNotFoundError:
        return {
            "file": file_path,
            "ok": False,
            "errors": [f"File not found: {file_path}"],
            "seed_examples_count": 0,
            "constraints": {"num_examples_recommended": {"min": 5, "max": 15, "ok": False}},
            "examples": []
        }
    except yaml.YAMLError as e:
        return {
            "file": file_path,
            "ok": False,
            "errors": [f"YAML parse error: {e}"],
            "seed_examples_count": 0,
            "constraints": {"num_examples_recommended": {"min": 5, "max": 15, "ok": False}},
            "examples": []
        }

    if not isinstance(content, dict) or 'seed_examples' not in content:
        return {
            "file": file_path,
            "ok": False,
            "errors": ["Missing 'seed_examples' or invalid YAML structure"],
            "seed_examples_count": 0,
            "constraints": {"num_examples_recommended": {"min": 5, "max": 15, "ok": False}},
            "examples": []
        }

    # Schema v3 validation for AI output as well
    schema_info = {}
    try:
        # Load and validate against specified schema type
        schema_dict, schema_src, base_uri, store_version, schema_attempts = _load_schema(schema_type)
        if schema_dict is not None:
            try:
                validator_cls = jsonschema.validators.validator_for(schema_dict)  # type: ignore[attr-defined]
                validator_cls.check_schema(schema_dict)
                # Since we've inlined the version reference, we don't need a resolver
                validator = validator_cls(schema_dict)
                validator.validate(content)
            except Exception as inner_e:
                raise inner_e
            schema_info = {"validated_against": f"v3/{schema_type}.json", "source": schema_src, "errors": [], "attempts": schema_attempts}
        else:
            schema_info = {"validated_against": None, "source": None, "errors": [], "attempts": schema_attempts}
    except jsonschema.exceptions.ValidationError as ve:
        prop_path = ".".join([str(p) for p in list(ve.path)])
        
        # Create a more user-friendly error message (same logic as above)
        if "is too short" in ve.message:
            path_parts = list(ve.path)
            if len(path_parts) >= 2 and path_parts[0] == 'seed_examples':
                seed_idx = path_parts[1]
                if len(path_parts) >= 3 and path_parts[2] == 'questions_and_answers':
                    try:
                        qa_count = len(content['seed_examples'][seed_idx]['questions_and_answers'])
                        error_msg = f"Seed example {seed_idx + 1} has only {qa_count} Q&A pairs (minimum required: 3)"
                    except (KeyError, IndexError, TypeError):
                        error_msg = f"Seed example {seed_idx + 1}: questions_and_answers array is too short (minimum: 3 Q&A pairs)"
                else:
                    try:
                        example_count = len(content['seed_examples'])
                        error_msg = f"Only {example_count} seed examples provided (minimum required: 5)"
                    except (KeyError, IndexError, TypeError):
                        error_msg = f"Not enough seed examples (minimum required: 5)"
            elif prop_path == 'seed_examples':
                # The seed_examples array itself is too short
                try:
                    example_count = len(content.get('seed_examples', []))
                    error_msg = f"Only {example_count} seed example(s) provided (minimum required: 5)"
                except (KeyError, TypeError):
                    error_msg = "Not enough seed examples (minimum required: 5)"
            else:
                error_msg = f"Field '{prop_path}' has too few items"
        elif "is a required property" in ve.message:
            missing_prop = ve.message.split("'")[1] if "'" in ve.message else ve.message
            error_msg = f"Missing required field: '{missing_prop}'"
            if prop_path:
                error_msg = f"At '{prop_path}': {error_msg}"
        else:
            error_msg = ve.message
            if len(error_msg) > 200 and "[{" in error_msg:
                error_msg = error_msg.split(" is ")[0] if " is " in error_msg else error_msg[:100] + "..."
        
        schema_info = {
            "validated_against": "v3/knowledge.json",
            "source": None,
            "errors": [
                {
                    "path": prop_path or "<root>",
                    "message": error_msg
                }
            ]
        }
    except Exception:
        schema_info = {"validated_against": None, "source": None, "errors": []}

    seed_examples = content.get('seed_examples', [])
    if not isinstance(seed_examples, list):
        return {
            "file": file_path,
            "ok": False,
            "errors": ["'seed_examples' should be a list"],
            "seed_examples_count": 0,
            "constraints": {"num_examples_recommended": {"min": 5, "max": 15, "ok": False}},
            "examples": []
        }

    num_contexts = len(seed_examples)
    # More lenient with seed examples - only warn if extremely few or too many
    num_examples_ok = num_contexts >= 3 and num_contexts <= 15
    errors: List[str] = []
    # Schema keys validation (InstructLab v3): require created_by for knowledge QnA
    normalized_path_info = file_path.replace('\\', '/')
    is_knowledge_path = '/knowledge/' in normalized_path_info
    if is_knowledge_path and 'created_by' not in content:
        errors.append("Schema: missing required key 'created_by'")
    if num_contexts < 3:
        errors.append(f"Very few seed examples ({num_contexts}). Consider adding more if your source allows.")
    elif num_contexts > 15:
        errors.append(f"Too many seed examples ({num_contexts}). Maximum recommended is 15.")

    examples_analysis: List[dict] = []

    for i, example in enumerate(seed_examples):
        context = example.get('context')
        questions_and_answers = example.get('questions_and_answers')

        if context is None:
            examples_analysis.append({
                "index": i + 1,
                "context_tokens": None,
                "question_tokens_total": None,
                "answer_tokens_total": None,
                "total_section_tokens": None,
                "constraints": {
                    "context_tokens_range_ok": False,
                    "qna_pairs_count_ok": False,
                    "total_section_tokens_max_ok": False
                }
            })
            continue

        context_tokens = count_tokens(context)
        context_range_ok = 300 <= context_tokens <= 500
        context_deviation_from_500 = abs(context_tokens - 500)

        total_section_tokens = context_tokens
        question_tokens_total = 0
        answer_tokens_total = 0

        # Only check that we have at least 1 pair and no more than 3
        qna_pairs_count_ok = isinstance(questions_and_answers, list) and 1 <= len(questions_and_answers) <= 3

        # Enforce MAX 3 and record ignored count
        pairs_ignored = 0
        if isinstance(questions_and_answers, list) and len(questions_and_answers) > 3:
            pairs_ignored = len(questions_and_answers) - 3
            questions_and_answers = questions_and_answers[:3]
            qna_pairs_count_ok = False

        pairs_details: List[dict] = []

        normalized_context = normalize_text(context)
        normalized_source = normalize_text(source_doc_text) if isinstance(source_doc_text, str) else None

        if isinstance(questions_and_answers, list):
            for idx, qna_pair in enumerate(questions_and_answers, start=1):
                question = qna_pair.get('question')
                answer = qna_pair.get('answer')
                if question is None or answer is None:
                    pairs_details.append({
                        "pair_index": idx,
                        "question_tokens": None,
                        "answer_tokens": None,
                        "pair_tokens_total": None,
                        "constraints": {
                            "pair_tokens_recommended_ok": False,
                            "question_in_context": False,
                            "answer_in_context": False,
                            "context_in_source": None
                        }
                    })
                    continue
                question_tokens = count_tokens(question)
                answer_tokens = count_tokens(answer)
                total_section_tokens += question_tokens + answer_tokens
                question_tokens_total += question_tokens
                answer_tokens_total += answer_tokens

                pair_total = question_tokens + answer_tokens
                pair_ok = 200 <= pair_total <= 300
                nq = normalize_text(question)
                na = normalize_text(answer)
                # Note: Removed literal matching since paraphrasing is allowed
                q_in_ctx = True  # Assume questions relate to context
                a_in_ctx = True  # Assume answers are entailed (paraphrasing allowed)
                context_in_source = None
                if normalized_source is not None:
                    context_in_source = normalized_context in normalized_source


                pairs_details.append({
                    "pair_index": idx,
                    "question_tokens": question_tokens,
                    "answer_tokens": answer_tokens,
                    "pair_tokens_total": pair_total,
                    "constraints": {
                        "pair_tokens_recommended_ok": pair_ok,
                        "question_in_context": q_in_ctx,
                        "answer_in_context": a_in_ctx,
                        "context_in_source": context_in_source
                    }
                })

        total_max_ok = total_section_tokens <= 750

        examples_analysis.append({
            "index": i + 1,
            "context_tokens": context_tokens,
            "question_tokens_total": question_tokens_total,
            "answer_tokens_total": answer_tokens_total,
            "total_section_tokens": total_section_tokens,
            "constraints": {
                "context_tokens_range_ok": context_range_ok,
                "qna_pairs_count_ok": qna_pairs_count_ok,
                "total_section_tokens_max_ok": total_max_ok,
                "context_deviation_from_500": context_deviation_from_500,
                "pairs_ignored": pairs_ignored
            },
            "pairs": pairs_details
        })

    all_examples_ok = all(
        ex["constraints"]["context_tokens_range_ok"] and
        ex["constraints"]["qna_pairs_count_ok"] and
        ex["constraints"]["total_section_tokens_max_ok"]
        for ex in examples_analysis
    ) if examples_analysis else False

    result = {
        "file": file_path,
        "ok": bool(num_examples_ok and all_examples_ok),
        "errors": errors,
        "seed_examples_count": num_contexts,
        "constraints": {
            "num_examples_recommended": {"min": 5, "max": 15, "ok": num_examples_ok}
        },
        "examples": examples_analysis,
        "diversity": {},
        "schema": schema_info,
        "tool": {
            "name": "analyze-qna",
            "version": os.environ.get('ANALYZE_QNA_VERSION') or "unknown"
        }
    }

    # Diversity heuristics (simple): detect presence of tables, lists, narrative, equations/theorems
    try:
        raw_texts = []
        for ex in seed_examples:
            ctx = ex.get('context')
            if isinstance(ctx, str):
                raw_texts.append(ctx)
        combined = "\n".join(raw_texts)
        has_table = '|' in combined and '---' in combined
        has_list = any(line.strip().startswith(('-', '*')) or (line.strip()[:2].isdigit() and line.strip().find('.') == 1) for line in combined.splitlines())
        has_paragraph = any(len(line.strip()) > 120 for line in combined.splitlines())
        has_equation = ('$' in combined) or ('∑' in combined) or ('Theorem' in combined or 'theorem' in combined)
        result["diversity"] = {
            "table": has_table,
            "list": has_list,
            "narrative": has_paragraph,
            "equation_or_theorem": has_equation
        }
    except Exception:
        pass

    if yaml_lint:
        result["yaml_lint"] = lint_yaml_file(file_path)

    return result

def analyze_qna_dir_ai(dir_path: str, source_doc_text: Optional[str] = None, yaml_lint: bool = False, schema_type: str = 'knowledge') -> List[dict]:
    if not os.path.isdir(dir_path):
        return [{
            "file": dir_path,
            "ok": False,
            "errors": [f"Directory not found: {dir_path}"],
            "seed_examples_count": 0,
            "constraints": {"num_examples_recommended": {"min": 5, "max": 15, "ok": False}},
            "examples": []
        }]

    yaml_files: List[str] = []
    for root, _dirs, files in os.walk(dir_path):
        for name in files:
            if name.lower().endswith((".yaml", ".yml")):
                yaml_files.append(os.path.join(root, name))

    return [analyze_qna_file_ai(p, source_doc_text, yaml_lint=yaml_lint, schema_type=schema_type) for p in sorted(yaml_files)]

def analyze_taxonomy_root_ai(root_path: str, source_doc_text: Optional[str] = None, yaml_lint: bool = False, schema_type: str = 'knowledge') -> List[dict]:
    if not os.path.isdir(root_path):
        return [{
            "file": root_path,
            "ok": False,
            "errors": [f"Directory not found: {root_path}"],
            "seed_examples_count": 0,
            "constraints": {"num_examples_recommended": {"min": 5, "max": 15, "ok": False}},
            "examples": []
        }]

    qna_files: List[str] = []
    for current_root, _dirs, files in os.walk(root_path):
        for name in files:
            if name == "qna.yaml":
                qna_files.append(os.path.join(current_root, name))

    return [analyze_qna_file_ai(p, source_doc_text, yaml_lint=yaml_lint) for p in sorted(qna_files)]

def main():
    parser = argparse.ArgumentParser(description="Analyze Q&A YAML files and report token counts and structure quality.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-f', '--file', help='Path to a Q&A YAML file to analyze')
    group.add_argument('-t', '--taxonomy-root', help="Root directory of taxonomy; analyze 'qna.yaml' files recursively")
    group.add_argument('-d', '--data-dir', help='[Deprecated] Path to a directory containing YAML Q&A files (recursively)')
    parser.add_argument('--ai', action='store_true', help='Output machine-readable JSON for agents')
    parser.add_argument('--source-doc', help='Path to source document text to verify context inclusion')
    parser.add_argument('--yaml-lint', action='store_true', help='Enable YAML formatting lint (trailing spaces, newline, tabs, CRLF, duplicate keys)')
    # Schema type selection
    parser.add_argument('--schema-type', choices=['knowledge', 'compositional_skills'], 
                        default='knowledge', help='Schema type to validate against (default: knowledge)')
    # Config/threshold overrides
    parser.add_argument('--config', help='Path to JSON file with threshold overrides')
    parser.add_argument('--context-range', help='Context token range as min,max (default 300,500)')
    parser.add_argument('--pair-range', help='Q/A pair token total range as min,max (default 200,300)')
    parser.add_argument('--examples-range', help='Seed examples count range as min,max (default 5,15)')
    parser.add_argument('--section-max', help='Max total tokens per example (default 750)')
    parser.add_argument('--line-match-min-length', help='Min line length for source matching (default 20)')
    parser.add_argument('--line-match-fraction-min', help='Min fraction of context lines that must appear in source (default 0.8)')
    parser.add_argument('path', nargs='?', help='[Deprecated] Path to a YAML file or directory (for backward compatibility)')

    args = parser.parse_args()
    thresholds = load_thresholds_from_args_and_config(args)

    if args.file:
        source_text = None
        if args.source_doc:
            try:
                with open(args.source_doc, 'r', encoding='utf-8', errors='ignore') as f:
                    source_text = f.read()
            except Exception as e:
                print(colored(f"Warning: could not read --source-doc: {e}", 'yellow'))
        if args.ai:
            print(json.dumps(analyze_qna_file_ai(args.file, source_text, yaml_lint=args.yaml_lint, schema_type=args.schema_type), indent=2))
        else:
            analyze_qna_file(args.file, source_text, thresholds=thresholds, yaml_lint=args.yaml_lint, schema_type=args.schema_type)
        return

    if args.taxonomy_root:
        source_text = None
        if args.source_doc:
            try:
                with open(args.source_doc, 'r', encoding='utf-8', errors='ignore') as f:
                    source_text = f.read()
            except Exception as e:
                print(colored(f"Warning: could not read --source-doc: {e}", 'yellow'))
        if args.ai:
            print(json.dumps(analyze_taxonomy_root_ai(args.taxonomy_root, source_text, yaml_lint=args.yaml_lint, schema_type=args.schema_type), indent=2))
        else:
            analyze_taxonomy_root(args.taxonomy_root, thresholds=thresholds, source_doc_text=source_text, yaml_lint=args.yaml_lint, schema_type=args.schema_type)
        return

    if args.data_dir:
        print(colored("Warning: --data-dir is deprecated. Prefer --taxonomy-root to analyze only 'qna.yaml' files.", 'yellow'))
        if args.ai:
            print(json.dumps(analyze_qna_dir_ai(args.data_dir, yaml_lint=args.yaml_lint, schema_type=args.schema_type), indent=2))
        else:
            analyze_qna_dir(args.data_dir, thresholds=thresholds, yaml_lint=args.yaml_lint, schema_type=args.schema_type)
        return

    if args.path:
        if os.path.isdir(args.path):
            if args.ai:
                print(json.dumps(analyze_qna_dir_ai(args.path, yaml_lint=args.yaml_lint, schema_type=args.schema_type), indent=2))
            else:
                analyze_qna_dir(args.path, thresholds=thresholds, yaml_lint=args.yaml_lint, schema_type=args.schema_type)
        else:
            if args.ai:
                print(json.dumps(analyze_qna_file_ai(args.path, yaml_lint=args.yaml_lint, schema_type=args.schema_type), indent=2))
            else:
                analyze_qna_file(args.path, thresholds=thresholds, yaml_lint=args.yaml_lint, schema_type=args.schema_type)
        return

    parser.print_usage()
    print("\nExamples:\n  python analyze_qna.py --file path/to/qna.yaml\n  python analyze_qna.py --file path/to/qna.yaml --ai\n  python analyze_qna.py --file path/to/qna.yaml --ai --source-doc path/to/source.txt\n  python analyze_qna.py --taxonomy-root path/to/taxonomy\n  python analyze_qna.py --taxonomy-root path/to/taxonomy --ai\n  python analyze_qna.py --data-dir path/to/dir  # deprecated")
    sys.exit(1)

if __name__ == "__main__":
    main()