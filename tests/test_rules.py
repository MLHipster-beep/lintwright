import os
import tempfile
import unittest
from pathlib import Path

import lintwright.rules  # noqa: F401  (registers the rule set)
from lintwright.model import run_rules
from lintwright.source import SourceContext
from tests.helpers import BASE_CHANGELOG, BASE_CONTROL, REPO_ROOT, base_files, make_tree


def tags(root: Path) -> set[str]:
    return {item.tag for item in run_rules(SourceContext(root).load())}


class RuleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, files):
        return make_tree(self.root, files)

    def test_clean_tree_produces_no_findings(self):
        self.assertEqual(tags(self.build(base_files())), set())

    def test_repository_packages_itself_cleanly(self):
        self.assertEqual(tags(REPO_ROOT), set())

    def test_missing_control(self):
        files = base_files()
        del files["debian/control"]
        self.assertIn("control-missing", tags(self.build(files)))

    def test_unparseable_control(self):
        self.build(base_files(**{"debian/control": "this is not a field\n"}))
        self.assertIn("control-parse-error", tags(self.root))

    def test_missing_source_stanza(self):
        control = "Package: demo\nArchitecture: all\nDescription: x\n longer\n"
        self.assertIn("control-missing-source-stanza", tags(self.build(base_files(**{"debian/control": control}))))

    def test_bad_maintainer(self):
        control = BASE_CONTROL.replace("Test Person <test@example.com>", "test@example.com")
        self.assertIn("control-invalid-maintainer", tags(self.build(base_files(**{"debian/control": control}))))

    def test_empty_extended_description(self):
        control = BASE_CONTROL.replace(
            "Description: a demonstration package\n Longer explanation of what the package does and why it exists.\n",
            "Description: a demonstration package\n",
        )
        self.assertIn("control-description", tags(self.build(base_files(**{"debian/control": control}))))

    def test_synopsis_too_long(self):
        long_line = "x" * 95
        control = BASE_CONTROL.replace("Description: a demonstration package", f"Description: {long_line}")
        self.assertIn("control-description", tags(self.build(base_files(**{"debian/control": control}))))

    def test_invalid_priority(self):
        control = BASE_CONTROL.replace("Priority: optional", "Priority: urgent")
        self.assertIn("control-invalid-priority", tags(self.build(base_files(**{"debian/control": control}))))

    def test_duplicate_package(self):
        control = BASE_CONTROL + (
            "\nPackage: demo\nArchitecture: all\nDescription: again\n with a body\n"
        )
        self.assertIn("control-duplicate-package", tags(self.build(base_files(**{"debian/control": control}))))

    def test_compat_declared_twice(self):
        files = base_files(**{"debian/compat": "13\n"})
        self.assertIn("debhelper-compat-conflict", tags(self.build(files)))

    def test_old_compat_level(self):
        control = BASE_CONTROL.replace("debhelper-compat (= 13)", "debhelper-compat (= 9)")
        self.assertIn("debhelper-compat-old", tags(self.build(base_files(**{"debian/control": control}))))

    def test_missing_compat(self):
        control = BASE_CONTROL.replace("Build-Depends: debhelper-compat (= 13)", "Build-Depends: dh-python")
        self.assertIn("debhelper-compat-missing", tags(self.build(base_files(**{"debian/control": control}))))

    def test_rules_shebang(self):
        files = base_files(**{"debian/rules": "#!/bin/sh\n%:\n\tdh $@\n"})
        self.assertIn("rules-shebang", tags(self.build(files)))

    def test_rules_not_executable(self):
        self.build(base_files())
        os.chmod(self.root / "debian" / "rules", 0o644)
        self.assertIn("rules-not-executable", tags(self.root))

    def test_legacy_source_format(self):
        self.assertIn("source-format-legacy", tags(self.build(base_files(**{"debian/source/format": "1.0\n"}))))

    def test_missing_source_format(self):
        files = base_files()
        del files["debian/source/format"]
        self.assertIn("source-format-missing", tags(self.build(files)))

    def test_unreleased_distribution(self):
        changelog = BASE_CHANGELOG.replace("noble;", "UNRELEASED;")
        self.assertIn("changelog-unreleased", tags(self.build(base_files(**{"debian/changelog": changelog}))))

    def test_invalid_urgency(self):
        changelog = BASE_CHANGELOG.replace("urgency=medium", "urgency=whenever")
        self.assertIn("changelog-invalid-urgency", tags(self.build(base_files(**{"debian/changelog": changelog}))))

    def test_missing_signature(self):
        changelog = "demo (1.0-1) noble; urgency=medium\n\n  * change\n"
        self.assertIn("changelog-signature", tags(self.build(base_files(**{"debian/changelog": changelog}))))

    def test_signer_mismatch(self):
        changelog = BASE_CHANGELOG.replace(
            " -- Test Person <test@example.com>",
            " -- Someone Else <else@example.com>",
        )
        self.assertIn("changelog-maintainer-mismatch", tags(self.build(base_files(**{"debian/changelog": changelog}))))

    def test_package_name_mismatch(self):
        changelog = BASE_CHANGELOG.replace("demo (1.0-1)", "other (1.0-1)")
        self.assertIn("changelog-package-mismatch", tags(self.build(base_files(**{"debian/changelog": changelog}))))

    def test_native_version_with_revision(self):
        files = base_files(**{"debian/source/format": "3.0 (native)\n"})
        self.assertIn("changelog-version-native", tags(self.build(files)))

    def test_missing_trailing_newline(self):
        files = base_files(**{"debian/changelog": BASE_CHANGELOG.rstrip("\n")})
        self.assertIn("changelog-no-trailing-newline", tags(self.build(files)))

    def test_usr_local_install_path(self):
        files = base_files(**{"debian/demo.install": "usr/local/bin/demo\n"})
        self.assertIn("install-path-usr-local", tags(self.build(files)))

    def test_manpage_missing_for_installed_binary(self):
        files = base_files(**{"debian/demo.install": "usr/bin/demo\n"})
        del files["debian/demo.1"]
        self.assertIn("manpage-missing", tags(self.build(files)))

    def test_maintainer_script_without_set_e(self):
        files = base_files(**{"debian/postinst": "#!/bin/sh\necho hi\n"})
        root = self.build(files)
        os.chmod(root / "debian" / "postinst", 0o755)
        self.assertIn("maintainer-script-no-set-e", tags(root))

    def test_missing_autopkgtest(self):
        files = base_files()
        del files["debian/tests/control"]
        self.assertIn("autopkgtest-missing", tags(self.build(files)))

    def test_missing_copyright(self):
        files = base_files()
        del files["debian/copyright"]
        self.assertIn("copyright-missing", tags(self.build(files)))


if __name__ == "__main__":
    unittest.main()
