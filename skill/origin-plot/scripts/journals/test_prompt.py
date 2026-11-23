"""Check journal prompt scope, distinction between defaults and rules, and the CLI."""

import subprocess
import sys
from pathlib import Path
import unittest

from journals import load_profile
from journals.prompt import journal_prompt


class JournalPrompts(unittest.TestCase):
    def test_sources_stage_and_default_are_drawn_from_each_profile(self):
        for id in ("nature", "science", "cell", "plos-one"):
            with self.subTest(id=id):
                p = load_profile(id)
                s = journal_prompt(id)
                self.assertIn(p["stage"], s)
                self.assertIn("项目绘图默认值", s)
                self.assertIn(p["checked"], s)
                for source in p["sources"]:
                    self.assertIn(source["url"], s)
                self.assertIn(f"python -m journals check {id}", s)
                self.assertLess(len(s), 1700)

    def test_strength_and_stage_of_numerical_guidance(self):
        self.assertIn("常用排版目标", journal_prompt("Nature"))
        self.assertIn("宽度上限", journal_prompt("Cell"))
        self.assertIn("建议约 6–8 pt", journal_prompt("cell"))
        self.assertIn("成图宽度须在 66.8–190.5 mm 内", journal_prompt("PLOS One"))
        self.assertIn("R 作图可提交 SVG", journal_prompt("Science"))
        with self.assertRaises(ValueError):
            journal_prompt("Nature Methods")

    def test_cli_returns_plain_text_for_agent_context(self):
        run = subprocess.run([sys.executable, "-B", "-m", "journals", "prompt", "science"],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, check=True)
        self.assertTrue(run.stdout.decode("utf8").startswith("为 Science 制作 Origin 图。"))


if __name__ == "__main__":
    unittest.main()
