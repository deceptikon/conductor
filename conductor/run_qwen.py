from workers.launch import launch_worker

# Try 1: qwen with qwen3-coder-flash (default mode -> Dash)
res = launch_worker(
    "qwen",
    "Hello, who are you?",
    model="qwen/qwen3-coder-flash",
    local_fallback=False,
    timeout=120,
)

print(f"[qwen] OK: {res.ok}")
print(f"[qwen] Return code: {res.returncode}")
print(f"[qwen] Text: {res.text[:500] if res.text else '(empty)'}")
print(f"[qwen] Error: {res.error[:500] if res.error else '(empty)'}")
print(f"[qwen] Command: {res.command}")
