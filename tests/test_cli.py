import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lintwright.cli import main
from tests.helpers import REPO_ROOT, base_files, make_tree


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_tree(Path(self._tmp.name), base_files())

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_exits_zero(self):
        code, _, _ = run_cli(["check", str(self.root), "--fail-on", "warning"])
        self.assertEqual(code, 0)

    def test_findings_exit_one(self):
        (self.root / "debian" / "source" / "format").unlink()
        code, out, _ = run_cli(["check", str(self.root), "--fail-on", "warning"])
        self.assertEqual(code, 1)
        self.assertIn("source-format-missing", out)

    def test_json_output_is_machine_readable(self):
        (self.root / "debian" / "source" / "format").unlink()
        code, out, _ = run_cli(["check", str(self.root), "--format", "json", "--fail-on", "warning"])
        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(payload["tool"], "lintwright")
        self.assertEqual(payload["summary"]["warning"], 1)
        self.assertEqual(payload["findings"][0]["path"], "debian/source/format")

    def test_fail_on_never_always_succeeds(self):
        (self.root / "debian" / "source" / "format").unlink()
        code, _, _ = run_cli(["check", str(self.root), "--fail-on", "never"])
        self.assertEqual(code, 0)

    def test_skip_silences_a_tag(self):
        (self.root / "debian" / "source" / "format").unlink()
        code, out, _ = run_cli(["check", str(self.root), "--skip", "source-format-missing", "--fail-on", "warning"])
        self.assertEqual(code, 0)
        self.assertNotIn("source-format-missing", out)

    def test_unknown_tag_is_a_usage_error(self):
        code, _, err = run_cli(["check", str(self.root), "--only", "not-a-tag"])
        self.assertEqual(code, 2)
        self.assertIn("unknown tag", err)

    def test_missing_directory_is_a_usage_error(self):
        code, _, _ = run_cli(["check", str(self.root / "does-not-exist")])
        self.assertEqual(code, 2)

    def test_rules_command_lists_every_rule(self):
        code, out, _ = run_cli(["rules"])
        self.assertEqual(code, 0)
        self.assertIn("control-missing", out)
        self.assertIn("rules", out.splitlines()[-1])

    def test_rules_json(self):
        code, out, _ = run_cli(["rules", "--format", "json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(all({"tag", "severity", "summary"} <= set(item) for item in payload))

    def test_repository_self_check_passes_in_ci_mode(self):
        code, _, _ = run_cli(["check", str(REPO_ROOT), "--fail-on", "info"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
