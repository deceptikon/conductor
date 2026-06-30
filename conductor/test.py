
from workers.launch import launch_worker

def test_backends():
    backends = ["qwen", "gemini", "claude"]
    prompt = "Hello, who are you? Please respond in one sentence."
    
    for backend in backends:
        print(f"\n--- Testing backend: {backend} (dash_mode='wt') ---")
        try:
            result = launch_worker(backend, prompt, dash_mode="wt")
            print(f"Status: {'OK' if result.ok else 'FAILED'}")
            print(f"Response: {result.text}")
        except Exception as e:
            print(f"Error running {backend}: {e}")

if __name__ == "__main__":
    test_backends()

