"""Discovery and loading of project-local agent skills."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SkillMetadata:
    """Metadata parsed from a skill's YAML front matter."""

    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None


@dataclass(frozen=True)
class Skill:
    """A validated skill and its Markdown instructions."""

    metadata: SkillMetadata
    directory: Path
    instructions: str

    def resolve_resource(self, relative_path: str) -> Path:
        """Resolve a resource while preventing access outside this skill."""
        requested = Path(relative_path)
        if requested.is_absolute():
            raise ValueError("Skill resources must use relative paths")

        root = self.directory.resolve()
        resource = (root / requested).resolve()
        if resource != root and root not in resource.parents:
            raise ValueError("Skill resource path escapes the skill directory")
        return resource


class SkillLoadError(ValueError):
    """Raised when a skill's SKILL.md cannot be validated."""


class SkillsManager:
    """Discover and retrieve skills from a project skills directory."""

    def __init__(self, skills_directory: Path | str) -> None:
        self.skills_directory = Path(skills_directory)
        self._skills: dict[str, Skill] = {}
        self.errors: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Reload all immediate child skill directories."""
        self._skills.clear()
        self.errors.clear()

        if not self.skills_directory.is_dir():
            return

        for directory in sorted(self.skills_directory.iterdir()):
            if not directory.is_dir():
                continue
            try:
                skill = self._load_skill(directory)
            except (OSError, SkillLoadError, yaml.YAMLError) as error:
                self.errors[directory.name] = str(error)
                continue

            key = skill.metadata.name.casefold()
            if key in self._skills:
                self.errors[directory.name] = (
                    f"duplicate skill name: {skill.metadata.name}"
                )
                continue
            self._skills[key] = skill

    def list_skills(self) -> list[Skill]:
        """Return discovered skills sorted by display name."""
        return sorted(self._skills.values(), key=lambda skill: skill.metadata.name.casefold())

    def get(self, name: str) -> Skill | None:
        """Return a skill by case-insensitive name."""
        return self._skills.get(name.strip().casefold())

    def format_instructions(self, skill: Skill) -> str:
        """Wrap skill instructions so they are distinct from user input."""
        return (
            "You are using the following Icebreaker skill. Apply it when it "
            "is relevant to the user's request. Do not claim to have used "
            "resources or tools that were not actually available.\n\n"
            f"Skill name: {skill.metadata.name}\n"
            f"Skill description: {skill.metadata.description}\n\n"
            "Begin skill instructions:\n"
            f"{skill.instructions}\n"
            "End skill instructions."
        )

    @staticmethod
    def _load_skill(directory: Path) -> Skill:
        skill_file = directory / "SKILL.md"
        if not skill_file.is_file():
            raise SkillLoadError("missing SKILL.md")

        content = skill_file.read_text(encoding="utf-8")
        metadata, instructions = SkillsManager._parse_skill_file(content)
        if directory.name.casefold() != metadata.name.casefold():
            raise SkillLoadError(
                f"directory name does not match metadata name '{metadata.name}'"
            )

        return Skill(metadata=metadata, directory=directory, instructions=instructions)

    @staticmethod
    def _parse_skill_file(content: str) -> tuple[SkillMetadata, str]:
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            raise SkillLoadError("SKILL.md must begin with YAML front matter")

        try:
            end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
        except StopIteration as error:
            raise SkillLoadError("SKILL.md has unterminated YAML front matter") from error

        raw_metadata: Any = yaml.safe_load("\n".join(lines[1:end]))
        if not isinstance(raw_metadata, dict):
            raise SkillLoadError("skill front matter must be a mapping")

        name = raw_metadata.get("name")
        description = raw_metadata.get("description")
        if not isinstance(name, str) or not name.strip():
            raise SkillLoadError("skill metadata requires a non-empty name")
        if not isinstance(description, str) or not description.strip():
            raise SkillLoadError("skill metadata requires a non-empty description")

        instructions = "\n".join(lines[end + 1 :]).strip()
        if not instructions:
            raise SkillLoadError("SKILL.md must contain skill instructions")

        return (
            SkillMetadata(
                name=name.strip(),
                description=description.strip(),
                license=_optional_string(raw_metadata.get("license")),
                compatibility=_optional_string(raw_metadata.get("compatibility")),
            ),
            instructions,
        )


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
