import sys
from pathlib import Path
import asyncio

def setup_dash_path():
    candidate = Path.home() / "X" / "dash"
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        print(f"Added {candidate} to sys.path")
    else:
        print(f"Candidate path {candidate} not found")

async def main():
    setup_dash_path()
    print("Attempting direct push via DashClient...")
    try:
        from dash_client import DashClient
        client = DashClient()
        # We use a dummy command to test connectivity
        ok = await client.push(
            worker="generic",
            command="echo 'Hello from direct client'",
            cwd=".",
            mode="sh"
        )
        print(f"Push result: {ok} (Type: {type(ok).__name__})")
    except ImportError:
        print("Error: dash_client module not found even after path setup")
    except Exception as e:
        print(f"Caught exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
