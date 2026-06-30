from workers.launch import launch_worker

if __name__ == "__main__":
    prompt = "Hello, this is a test prompt for the generic worker."
    print(f"Launching generic worker with prompt: {prompt}")

    try:
        result = launch_worker(
            worker_name="_openai_generic",
            prompt=prompt,
        )
        print("\n--- Worker Result ---")
        print(f"Success: {result.ok}")
        print(f"Text: {result.text}")
    except Exception as e:
        print(f"An error occurred: {e}")
