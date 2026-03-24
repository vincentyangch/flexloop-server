import json
from pathlib import Path


class PromptManager:
    def __init__(self, prompts_dir: Path | str):
        self.prompts_dir = Path(prompts_dir)
        manifest_path = self.prompts_dir / "manifest.json"
        with open(manifest_path) as f:
            self.manifest = json.load(f)

    def get_prompt(self, prompt_type: str, provider: str = "default") -> str:
        if prompt_type not in self.manifest:
            raise KeyError(f"Unknown prompt type: {prompt_type}")

        versions = self.manifest[prompt_type]
        version = versions.get(provider, versions.get("default"))
        if not version:
            raise KeyError(f"No version found for {prompt_type}/{provider}")

        prompt_path = self.prompts_dir / prompt_type / f"{version}.md"
        return prompt_path.read_text()

    def render(self, prompt_type: str, provider: str = "default", **kwargs) -> str:
        template = self.get_prompt(prompt_type, provider)
        for key, value in kwargs.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        return template
