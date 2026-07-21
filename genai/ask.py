"""Single-shot CLI: python -m genai.ask "How many trips were there?" """
import argparse
import sys

from genai.pipeline import ask
from genai.types import LLMError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chat with the NYC taxi warehouse.")
    parser.add_argument("question", help="Your question, in quotes.")
    args = parser.parse_args(argv)

    try:
        state = ask(args.question)
    except LLMError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nANSWER:\n{state['answer']}\n")
    if not state.get("refused"):
        print(f"SQL USED:\n{state['sql']}\n")
        print(f"SCANNED: {state.get('scanned_bytes', 0) / 1e9:.4f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
