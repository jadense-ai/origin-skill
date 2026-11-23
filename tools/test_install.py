"""Regression cases for installing into existing project configuration."""
import json
import hashlib
import tempfile
import tomllib
import unittest
from pathlib import Path

from install import host_configs, install_locked, json_put, jsonc_value


class ExistingProject(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.project = Path(self.scratch.name) / "论文 图"
        self.project.mkdir()
        self.launch = self.project / ".origin-plot/launch.py"

    def test_three_configurations_are_repeatable(self):
        clients = {"claude", "codex", "opencode"}
        files = host_configs(self.project, clients, self.launch)
        self.assertEqual(len(files), 3)
        for path, content in files.items():
            path.parent.mkdir(exist_ok=True)
            path.write_text(content, encoding="utf-8")
        codex = tomllib.loads(files[self.project / ".codex/config.toml"])["mcp_servers"]
        self.assertEqual(codex["origin-plot"]["args"], [str(self.launch), "isolated"])
        claude = json.loads(files[self.project / ".mcp.json"])["mcpServers"]
        self.assertEqual(claude["origin-plot-current"]["args"], [str(self.launch), "attach"])
        self.assertEqual(host_configs(self.project, clients, self.launch), {})

    def test_jsonc_preserves_other_fields_and_comments(self):
        path = self.project / "opencode.jsonc"
        content = '{"misc":{"servers":{}}, "mcp":{"local-other":{"type":"local", "command":["tool"],},}, // retain\n}'
        path.write_text(content, encoding="utf-8")
        changed = host_configs(self.project, {"opencode"}, self.launch)[path]
        self.assertIn("// retain", changed)
        mcp = jsonc_value(changed)["mcp"]
        self.assertIn("local-other", mcp)
        self.assertIn("origin-plot", mcp)
        self.assertNotIn("servers", mcp)

    def test_nested_existing_layout_and_same_name_conflict(self):
        path = self.project / "opencode.jsonc"
        path.write_text('{"mcp":{"servers":{}}}',encoding="utf-8")
        changed = host_configs(self.project, {"opencode"}, self.launch)[path]
        self.assertIn("origin-plot", jsonc_value(changed)["mcp"]["servers"])
        with self.assertRaises(ValueError):
            json_put('{"mcpServers":{"origin-plot":{"command":"original"}}}',
                     ["mcpServers","origin-plot"], {"command":"new"})

    def test_retry_after_interrupted_mirror_preserves_user_edits(self):
        runtime = self.project / ".origin-plot"
        payload = runtime / "releases/test"
        payload.mkdir(parents=True)
        (payload / "ready").touch()  # This case exercises mirror recovery after offline pip completed.
        bundle = Path(self.scratch.name) / "bundle"
        src = bundle / "skill/origin-plot"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_bytes(b"version one")
        (bundle / "launch.py").write_text("# launch",encoding="utf-8")
        manifest = {"version":"test", "files":{"skill/origin-plot/SKILL.md":hashlib.sha256(b"version one").hexdigest()}}
        mirror = self.project / ".agents/skills/origin-plot"
        mirror.mkdir(parents=True)
        (runtime / "install-pending.json").write_text(json.dumps({"payload":str(payload),
            "clients":["codex"], "mirrors":[str(mirror)]}),encoding="utf-8")
        install_locked(bundle, self.project, {"codex"}, manifest, runtime, payload)
        self.assertFalse((runtime / "install-pending.json").exists())
        self.assertEqual((mirror / "SKILL.md").read_bytes(), b"version one")
        (mirror / "SKILL.md").write_bytes(b"local customizations")
        with self.assertRaises(ValueError):
            install_locked(bundle, self.project, {"codex"}, manifest, runtime, payload)
        self.assertEqual((mirror / "SKILL.md").read_bytes(), b"local customizations")


if __name__ == "__main__":
    unittest.main()
