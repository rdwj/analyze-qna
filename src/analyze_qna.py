"""
This script analyzes a Q&A YAML file and generates a concise report.
Usage: python analyze_qna.py <path_to_qna.yaml>

It is recommended to use a venv with the following packages installed:
- pyyaml
- tiktoken
- tabulate
- termcolor
- mistral-common (for Mistral tokenization, optional)

"""
import os
import sys
import yaml
import tiktoken
from mistral_common.protocol.instruct.messages import (
    AssistantMessage,
    UserMessage,
    ToolMessage
)
from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
from mistral_common.protocol.instruct.tool_calls import Function, Tool, ToolCall, FunctionCall
from mistral_common.protocol.instruct.request import ChatCompletionRequest
from tabulate import tabulate
from termcolor import colored
from typing import List, Dict

# Magic constants
TOKEN_COUNTER = "openai"

def count_tokens(text: str) -> int:
    """Count the number of tokens in a text using the specified tokenizer."""
    if TOKEN_COUNTER == "mistral":
        return count_tokens_mistral(text)
    elif TOKEN_COUNTER == "openai":
        return count_tokens_openai(text)
    else:
        raise ValueError(f"Unknown token counter: {TOKEN_COUNTER}")

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

# For future development. This doesn't work yet. When the documentation for this tokenizer is updated, I will try again.
# This is based on https://github.com/mistralai/mistral-common
def count_tokens_mistral(text: str, model_name="open-mixtral-8x22b") -> int:
    """Count the number of tokens in a text using Mistral's tokenizer."""
    try:
        tokenizer_v3 = MistralTokenizer.v3()


        tokenized = tokenizer_v3.encode_chat_completion(
            ChatCompletionRequest(
                messages=[
                    UserMessage(content=text)
                ],
                model="mixtral_8x7b",
            )
        )

        tokens, text = tokenized.tokens, tokenized.text

        # tokenized = tokenizer_v3.encode_chat_completion(
        #     ChatCompletionRequest(
        #         messages=[
        #             UserMessage(text),
        #         ],
        #         model="test",
        #     )
        # )

        # tokens = tokenized.tokens
        return len(tokens)
    except ImportError:
        print(colored("Error: Please ensure you have the 'mistral-common' library correctly installed.", 'red', attrs=['bold']))
        return 0
    except KeyError:
        print(colored(f"Error: Tokenizer for model '{model_name}' not found.", 'red', attrs=['bold']))
        return 0
    except Exception as e:
        print(colored(f"Error during Mistral tokenization: {e}", 'red', attrs=['bold']))
        return 0

def analyze_qna_file(file_path: str) -> None:
    """Analyzes a qna.yaml file and generates a concise report using the tabulate library with Mistral's tokenizer."""
    try:
        with open(file_path, 'r') as file:
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
    if not 5 <= num_contexts <= 15:
        print(colored(f"Warning: Expected between 5 and 15 context sections, found {num_contexts}.", 'yellow'))

    report_data = []

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
        if not 300 <= context_tokens <= 500:
            status = f"Context Tokens: {context_tokens} (Expected 300-500)"
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

        if not isinstance(questions_and_answers, list) or len(questions_and_answers) != 3:
            if status == "OK":
                status = f"Expected 3 Q&A pairs, found {len(questions_and_answers) if isinstance(questions_and_answers, list) else 0}"
                status_color = 'red'

        for j, qna_pair in enumerate(questions_and_answers):
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

        if total_section_tokens > 750:
            status = f"Total Section Tokens: {total_section_tokens} (Max 750)"
            status_color = 'red'

        report_data.append([
            i + 1,
            colored(str(context_tokens), 'yellow') if not 300 <= context_tokens <= 500 else context_tokens,
            question_tokens_total,
            answer_tokens_total,
            colored(str(total_section_tokens), 'red', attrs=['bold']) if total_section_tokens > 750 else total_section_tokens,
            colored(status, status_color)
        ])

    if report_data:
        headers = ["Index", "C-Tokens", "Q-Tokens", "A-Tokens", "Total", "Status"]
        print(colored("\nQ&A Analysis Report:", 'blue', attrs=['bold']))
        print(tabulate(report_data, headers=headers, tablefmt="grid"))
    else:
        print(colored("\nNo seed examples found to analyze.", 'yellow'))

    print(colored("\nAnalysis complete.", 'green'))

def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze_qna.py <path_to_qna.yaml>")
        sys.exit(1)

    file_path = sys.argv[1]
    analyze_qna_file(file_path)

if __name__ == "__main__":
    main()