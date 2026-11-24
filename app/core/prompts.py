import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt template file from the prompts directory."""
    filepath = PROMPTS_DIR / filename
    if not filepath.is_file():
        raise FileNotFoundError(f"Prompt template not found: {filepath}")
    return filepath.read_text(encoding="utf-8")


def get_prompt_version() -> str:
    """Extract the prompt version tag from system.md (defaults to 'v1')."""
    content = load_prompt("system.md")
    match = re.search(r"<!--\s*version:\s*([a-zA-Z0-9._-]+)\s*-->", content)
    return match.group(1) if match else "v1"


def get_system_prompt() -> str:
    """Return the system prompt text."""
    return load_prompt("system.md")


def render_classify_prompt(message: str) -> str:
    """Inject the ticket message safely into classify.md."""
    template = load_prompt("classify.md")
    return template.replace("{message}", message)


def render_repair_prompt(raw_output: str, validation_error: str) -> str:
    """Inject broken output and error details safely into repair.md."""
    template = load_prompt("repair.md")
    return template.replace("{raw_output}", raw_output).replace(
        "{validation_error}", validation_error
    )
