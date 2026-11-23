"""Protect the new default host and explicit, strictly checked legacy access."""
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("deployment_remote", Path(__file__).resolve().parents[1] / "remote.py")
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


class RemoteTargetTests(unittest.TestCase):
    def test_default_uses_verified_replacement_and_strict_known_hosts(self):
        arguments = remote.ssh_arguments()
        self.assertEqual(arguments[-1], "root@121.40.113.185")
        self.assertIn("StrictHostKeyChecking=yes", arguments)
        self.assertIn("BatchMode=yes", arguments)
        self.assertIn("HostKeyAlgorithms=ssh-ed25519", arguments)
        self.assertIn(f'UserKnownHostsFile="{(remote.ROOT / ".local/ssh/known_hosts").as_posix()}"', arguments)
        self.assertIn(str(remote.ROOT / ".local/ssh/blog_deploy_ed25519"), arguments)

    def test_legacy_requires_explicit_selection_without_disabling_verification(self):
        arguments = remote.ssh_arguments(host=remote.LEGACY_HOST)
        self.assertEqual(arguments[-1], "root@101.37.147.237")
        self.assertIn("StrictHostKeyChecking=yes", arguments)
        self.assertIn("IdentitiesOnly=yes", arguments)

    def test_option_injection_and_shell_text_are_not_hosts(self):
        for value in ("-oStrictHostKeyChecking=no", "121.40.113.185;id", "root@121.40.113.185", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.ssh_arguments(host=value)


if __name__ == "__main__":
    unittest.main()
