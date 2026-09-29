import tempfile
import unittest
from pathlib import Path

from skills_manager import SkillsManager


class SkillsManagerTests(unittest.TestCase):
    def test_discovers_skill_with_multiline_description(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill_directory = root / "example-skill"
            skill_directory.mkdir()
            (skill_directory / "SKILL.md").write_text(
                "---\n"
                "name: example-skill\n"
                "description: >\n"
                "  An example skill.\n"
                "license: MIT\n"
                "---\n\n"
                "# Example\n\nFollow these instructions.\n",
                encoding="utf-8",
            )

            manager = SkillsManager(root)
            skill = manager.get("EXAMPLE-SKILL")

            self.assertIsNotNone(skill)
            assert skill is not None
            self.assertEqual(skill.metadata.description, "An example skill.")
            self.assertIn("Follow these instructions", skill.instructions)
            self.assertIn("Skill name: example-skill", manager.format_instructions(skill))

    def test_invalid_skill_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_directory = root / "invalid-skill"
            invalid_directory.mkdir()
            (invalid_directory / "SKILL.md").write_text(
                "# Missing front matter\n", encoding="utf-8"
            )

            manager = SkillsManager(root)

            self.assertEqual(manager.list_skills(), [])
            self.assertIn("invalid-skill", manager.errors)

    def test_resource_resolution_cannot_escape_skill_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill_directory = root / "example-skill"
            skill_directory.mkdir()
            (skill_directory / "SKILL.md").write_text(
                "---\nname: example-skill\ndescription: Example\n---\n\nInstructions\n",
                encoding="utf-8",
            )
            manager = SkillsManager(root)
            skill = manager.get("example-skill")
            assert skill is not None

            with self.assertRaises(ValueError):
                skill.resolve_resource("../outside.txt")


if __name__ == "__main__":
    unittest.main()
