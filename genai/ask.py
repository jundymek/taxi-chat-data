"""Single-shot CLI: python -m genai.ask "Ile było przejazdów?" """
import argparse
import sys

from genai.pipeline import ask
from genai.types import LLMError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chat with the NYC taxi warehouse (Polish).")
    parser.add_argument("question", help="Pytanie po polsku, w cudzysłowie.")
    args = parser.parse_args(argv)

    try:
        state = ask(args.question)
    except LLMError as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1

    print(f"\nODPOWIEDŹ:\n{state['answer']}\n")
    if not state.get("refused"):
        print(f"UŻYTY SQL:\n{state['sql']}\n")
        print(f"ZESKANOWANO: {state.get('scanned_bytes', 0) / 1e9:.4f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
