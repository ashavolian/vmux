"""Run with:  python3 -m unittest discover -s tests"""

import getpass
import io
import json
import os
import shlex
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
vmux = SourceFileLoader("vmux", os.path.join(HERE, "..", "vmux")).load_module()


def write(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_none(self):
        self.assertIsNone(vmux.load_config(self.path))

    def test_user_placeholder_is_quoted_only_in_commands(self):
        user = getpass.getuser()
        write(self.path, {
            "host": "{user}.example.com",
            "vm_status_command": "cloud status {user}",
            "vm_running_pattern": "^{user} RUNNING$",
            "auth_fatal_markers": ["{user} oauth"],
        })
        cfg = vmux.load_config(self.path)
        self.assertEqual(cfg.host, f"{user}.example.com")
        self.assertEqual(cfg.vm_status_command, f"cloud status {shlex.quote(user)}")
        self.assertEqual(cfg.vm_running_pattern, f"^{user} RUNNING$")
        self.assertEqual(cfg.auth_fatal_markers, [f"{user} oauth"])

    def test_unknown_key_is_warned_and_ignored(self):
        write(self.path, {"host": "h", "colour": "blue"})
        out = io.StringIO()
        with redirect_stdout(out):
            cfg = vmux.load_config(self.path)
        self.assertEqual(cfg.host, "h")
        self.assertIn("colour", out.getvalue())

    def test_bad_regex_exits(self):
        write(self.path, {"host": "h", "vm_running_pattern": "("})
        with self.assertRaises(SystemExit):
            vmux.load_config(self.path)

    def test_wrong_type_exits(self):
        write(self.path, {"host": 42})
        with self.assertRaises(SystemExit):
            vmux.load_config(self.path)

    def test_save_is_owner_only_and_round_trips(self):
        cfg = vmux.Config(host="box", claude_flags="--x", auth_fatal_markers=["m"])
        vmux.save_config(self.path, cfg)
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(vmux.load_config(self.path), cfg)


class ClaudeCommandTests(unittest.TestCase):
    def tearDown(self):
        vmux.CFG = vmux.Config()

    def test_model_is_quoted_for_the_inner_shell(self):
        vmux.CFG = vmux.Config(claude_model="some-model[1m]", claude_flags="--flag x")
        self.assertEqual(
            vmux.claude_cmd("abc", resume=False),
            "claude --session-id abc --model 'some-model[1m]' --flag x",
        )

    def test_blank_model_and_flags_are_omitted(self):
        vmux.CFG = vmux.Config()
        self.assertEqual(vmux.claude_cmd("abc", resume=True), "claude --resume abc")


class VmStatusTests(unittest.TestCase):
    def tearDown(self):
        vmux.CFG = vmux.Config()

    def configure(self, output):
        vmux.CFG = vmux.Config(
            vm_status_command="printf %s " + shlex.quote(output),
            vm_running_pattern=r"^\s*box\s.*\b(RUNNING)\b",
            vm_stopped_pattern=r"^\s*box\s.*\b(TERMINATED|STOPPING|SUSPENDED)\b",
        )

    def test_running(self):
        self.configure("NAME  ZONE  STATUS\nbox   z1    RUNNING\nother z1 TERMINATED\n")
        self.assertEqual(vmux.vm_status(), ("running", "RUNNING"))

    def test_stopped_reports_the_matched_state(self):
        self.configure("NAME  ZONE  IP  STATUS\nbox   z1        TERMINATED\n")
        self.assertEqual(vmux.vm_status(), ("stopped", "TERMINATED"))

    def test_unrecognised_output_is_unknown_not_stopped(self):
        self.configure("Please log in to continue\n")
        state, _ = vmux.vm_status()
        self.assertIsNone(state)

    def test_not_configured_is_unknown(self):
        vmux.CFG = vmux.Config()
        self.assertIsNone(vmux.vm_status()[0])


class AuthTests(unittest.TestCase):
    def tearDown(self):
        vmux.CFG = vmux.Config()

    def test_site_markers_extend_the_builtin_one(self):
        vmux.CFG = vmux.Config(auth_fatal_markers=["Error generating token"])
        self.assertTrue(vmux.is_auth_infra_error("bind: address already in use"))
        self.assertTrue(vmux.is_auth_infra_error("sso: error generating TOKEN"))
        self.assertFalse(vmux.is_auth_infra_error("Permission denied (publickey)"))


class NameTests(unittest.TestCase):
    def test_prefix_and_validation(self):
        self.assertEqual(vmux.normalize_name("fix-tests"), "claude-fix-tests")
        self.assertEqual(vmux.normalize_name("claude-x"), "claude-x")
        self.assertTrue(vmux.valid_name("claude-a_b-1"))
        self.assertFalse(vmux.valid_name("has space"))
        self.assertFalse(vmux.valid_name(""))


if __name__ == "__main__":
    unittest.main()
