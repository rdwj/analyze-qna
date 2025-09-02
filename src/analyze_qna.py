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

def analyze_qna_file(file_path: str, source_doc_text: Optional[str] = None, thresholds: Optional[Dict[str, Any]] = None) -> None:
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

    if 'seed_examples' not in content:
        print(colored("Warning: No 'seed_examples' section found in the YAML file.", 'yellow'))
        return

    seed_examples = content.get('seed_examples', [])
    if not isinstance(seed_examples, list):
        print(colored("Error: 'seed_examples' should be a list.", 'red', attrs=['bold']))
        return

    num_contexts = len(seed_examples)
    if not thresholds["examples_min"] <= num_contexts <= thresholds["examples_max"]:
        print(colored(f"Warning: Expected between {thresholds['examples_min']} and {thresholds['examples_max']} context sections, found {num_contexts}.", 'yellow'))

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

        if len(questions_and_answers) != 3:
            if status == "OK":
                status = f"Expected 3 Q&A pairs, found {len(questions_and_answers) if isinstance(questions_and_answers, list) else 0}"
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

            # Ensure Q and A are present in context (loose check)
            nq = normalize_text(question)
            na = normalize_text(answer)
            q_in_ctx = nq in normalized_context
            a_in_ctx = na in normalized_context
            if not q_in_ctx or not a_in_ctx:
                extra_warnings.append(f"Example {i+1}: Q or A not fully present in context")

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

    print(colored("\nAnalysis complete.", 'green'))

def analyze_qna_dir(dir_path: str, thresholds: Optional[Dict[str, Any]] = None, source_doc_text: Optional[str] = None) -> None:
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
        analyze_qna_file(file_path, source_doc_text=source_doc_text, thresholds=thresholds)

def analyze_taxonomy_root(root_path: str, thresholds: Optional[Dict[str, Any]] = None, source_doc_text: Optional[str] = None) -> None:
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
        analyze_qna_file(file_path, source_doc_text=source_doc_text, thresholds=thresholds)

def analyze_qna_file_ai(file_path: str, source_doc_text: Optional[str] = None) -> dict:
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
    num_examples_ok = 5 <= num_contexts <= 15
    errors: List[str] = []
    if not num_examples_ok:
        errors.append(f"Expected 5-15 seed examples, found {num_contexts}")

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

        qna_pairs_count_ok = isinstance(questions_and_answers, list) and len(questions_and_answers) == 3

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
                q_in_ctx = nq in normalized_context
                a_in_ctx = na in normalized_context
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
        "diversity": {}
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

    return result

def analyze_qna_dir_ai(dir_path: str, source_doc_text: Optional[str] = None) -> List[dict]:
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

    return [analyze_qna_file_ai(p, source_doc_text) for p in sorted(yaml_files)]

def analyze_taxonomy_root_ai(root_path: str, source_doc_text: Optional[str] = None) -> List[dict]:
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

    return [analyze_qna_file_ai(p, source_doc_text) for p in sorted(qna_files)]

def main():
    parser = argparse.ArgumentParser(description="Analyze Q&A YAML files and report token counts and structure quality.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-f', '--file', help='Path to a Q&A YAML file to analyze')
    group.add_argument('-t', '--taxonomy-root', help="Root directory of taxonomy; analyze 'qna.yaml' files recursively")
    group.add_argument('-d', '--data-dir', help='[Deprecated] Path to a directory containing YAML Q&A files (recursively)')
    parser.add_argument('--ai', action='store_true', help='Output machine-readable JSON for agents')
    parser.add_argument('--source-doc', help='Path to source document text to verify context inclusion')
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
            print(json.dumps(analyze_qna_file_ai(args.file, source_text), indent=2))
        else:
            analyze_qna_file(args.file, source_text, thresholds=thresholds)
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
            print(json.dumps(analyze_taxonomy_root_ai(args.taxonomy_root, source_text), indent=2))
        else:
            analyze_taxonomy_root(args.taxonomy_root, thresholds=thresholds, source_doc_text=source_text)
        return

    if args.data_dir:
        print(colored("Warning: --data-dir is deprecated. Prefer --taxonomy-root to analyze only 'qna.yaml' files.", 'yellow'))
        if args.ai:
            print(json.dumps(analyze_qna_dir_ai(args.data_dir), indent=2))
        else:
            analyze_qna_dir(args.data_dir, thresholds=thresholds)
        return

    if args.path:
        if os.path.isdir(args.path):
            if args.ai:
                print(json.dumps(analyze_qna_dir_ai(args.path), indent=2))
            else:
                analyze_qna_dir(args.path, thresholds=thresholds)
        else:
            if args.ai:
                print(json.dumps(analyze_qna_file_ai(args.path), indent=2))
            else:
                analyze_qna_file(args.path, thresholds=thresholds)
        return

    parser.print_usage()
    print("\nExamples:\n  python analyze_qna.py --file path/to/qna.yaml\n  python analyze_qna.py --file path/to/qna.yaml --ai\n  python analyze_qna.py --file path/to/qna.yaml --ai --source-doc path/to/source.txt\n  python analyze_qna.py --taxonomy-root path/to/taxonomy\n  python analyze_qna.py --taxonomy-root path/to/taxonomy --ai\n  python analyze_qna.py --data-dir path/to/dir  # deprecated")
    sys.exit(1)

if __name__ == "__main__":
    main()