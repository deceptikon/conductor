from workers.launch import launch_worker

res = launch_worker(
    "gemini",
    "Hello, who are you?",
    model=None,
    local_fallback=False,
    timeout=120,
)

print(f"[gemini] OK: {res.ok}")
print(f"[gemini] Return code: {res.returncode}")
print(f"[gemini] Text: {res.text[:500] if res.text else '(empty)'}")
print(f"[gemini] Error: {res.error[:500] if res.error else '(empty)'}")
print(f"[gemini] Cmd: {res.cmd}")
