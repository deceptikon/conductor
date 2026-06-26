import os

import requests

LLAMA_URL = "http://127.0.0.1:22222/api/completion"
CONTEXT_WINDOW = 16384


class NarrativeAgent:
    def __init__(self, vault_path):
        self.vault_path = os.path.abspath(vault_path)
        self.system_prompt = (
            "You are a narrative review agent. The provided context is a hierarchical "
            "representation of the story world. Use STORY-X notes for specific plot beats, "
            "EPIC notes for overarching arcs, and legal/spec notes for factual grounding. "
            "Evaluate for narrative coherence and internal contradiction."
        )

    def get_relevant_notes(self, search_paths):
        """Walk the vault tree and assemble context from specified paths."""
        context_str = ""
        for path_suffix in search_paths:
            root = os.path.join(self.vault_path, path_suffix)
            if not os.path.exists(root):
                continue
            for root, _, files in os.walk(root):
                for file in files:
                    if file.endswith(".md"):
                        source_file = os.path.join(root, file)
                        content = open(source_file, encoding="utf-8").read()
                        context_str += f"\n--- SOURCE: {file} ---\n{content}\n"
        return context_str

    def run(self, task, search_paths=None):
        if search_paths is None:
            search_paths = ["00_Project", "20_Specs", "99_Archive"]

        context = self.get_relevant_notes(search_paths)
        user_input = f"TASK: {task}\n\nCONTEXT:\n{context}"

        payload = {
            "prompt": f"{self.system_prompt}\n\nUSER INPUT:\n{user_input}",
            "n_predict": 2048,
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64,
        }

        response = requests.post(LLAMA_URL, json=payload)
        response.raise_for_status()
        return response.json()["content"]


if __name__ == "__main__":
    agent = NarrativeAgent(vault_path="adlai-vault")
    # You can override search_paths here for a specific review (e.g. just the Specs)
    result = agent.run(
        "Review the latest storyboard for narrative consistency.",
        search_paths=["20_Specs", "99_Archive"],
    )
    print(f"\nAGENT OUTPUT:\n{result}\n")
