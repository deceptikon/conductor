"""OpenAI-compatible API runner for GenericOpenAIBackend.

Uses only stdlib (urllib) so there are no extra dependencies.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI-compatible generic runner")
    parser.add_argument("--base-url", required=True, help="API base URL (e.g. http://127.0.0.1:22222/v1)")
    parser.add_argument("--model", required=True, help="Model identifier")
    parser.add_argument("prompt", nargs="?", default="", help="User prompt")
    args = parser.parse_args()

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "stream": False,
    }
    data = json.dumps(payload).encode()

    req = urllib.request.Request(
        f"{args.base_url}/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.load(resp)
            content = result["choices"][0]["message"]["content"]
            print(content)
            return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
