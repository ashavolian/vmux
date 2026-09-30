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

    def test_defaults(self):
        write(self.path, {"host": "h"})
        cfg = vmux.load_config(self.path)
        self.assertEqual(cfg.herdr_command, "herdr")
        self.assertEqual(cfg.workdir, "$HOME")
        self.assertFalse(cfg.has_vm_control)

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


class ClaudeArgsTests(unittest.TestCase):
    def tearDown(self):
        vmux.CFG = vmux.Config()

    def test_model_is_quoted_for_the_inner_shell(self):
        vmux.CFG = vmux.Config(claude_model="some-model[1m]", claude_flags="--flag x")
        self.assertEqual(
            vmux.claude_args("abc"),
            "--session-id abc --model 'some-model[1m]' --flag x",
        )

    def test_blank_model_and_flags_are_omitted(self):
        vmux.CFG = vmux.Config()
        self.assertEqual(vmux.claude_args("abc"), "--session-id abc")


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

    def test_unresolvable_host_detection(self):
        self.assertTrue(vmux.is_host_unresolvable(
            "ssh: Could not resolve hostname x: nodename nor servname provided"))
        self.assertFalse(vmux.is_host_unresolvable("Connection timed out"))


class NameTests(unittest.TestCase):
    def test_prefix_and_validation(self):
        self.assertEqual(vmux.normalize_name("fix-tests"), "claude-fix-tests")
        self.assertEqual(vmux.normalize_name("claude-x"), "claude-x")
        self.assertTrue(vmux.valid_name("claude-a_b-1"))
        self.assertFalse(vmux.valid_name("has space"))
        self.assertFalse(vmux.valid_name(""))


class HerdrTests(unittest.TestCase):
    def test_agent_names_fit_herdrs_rules(self):
        for raw, want in (
            ("claude-fix-tests", "claude-fix-tests"),
            ("claude-0930-141502", "claude-0930-141502"),
            ("Claude_Mixed.Case", "claude_mixed-case"),
            ("123", "c-123"),
            ("", "claude"),
            ("claude-" + "x" * 40, ("claude-" + "x" * 40)[:32]),
        ):
            got = vmux.herdr_agent_name(raw)
            self.assertEqual(got, want)
            self.assertRegex(got, r"^[a-z][a-z0-9_-]{0,31}$")

    def test_ids_come_bare_or_wrapped(self):
        self.assertEqual(vmux.herdr_id("w1:p1", "pane_id"), "w1:p1")
        self.assertEqual(vmux.herdr_id({"pane_id": "w2:p1", "x": 1}, "pane_id"), "w2:p1")
        self.assertEqual(vmux.herdr_id({"id": "w3"}, "workspace_id", "id"), "w3")
        self.assertEqual(vmux.herdr_id(None, "pane_id"), "")

    def test_error_extraction(self):
        self.assertEqual(
            vmux.herdr_error('{"error":{"code":"agent_not_ready","message":"pane busy"}}'),
            "pane busy",
        )
        self.assertEqual(vmux.herdr_error("", "plain text failure"), "plain text failure")
        self.assertEqual(vmux.herdr_error(""), "")

    def test_remote_login_wraps_in_a_login_shell(self):
        self.assertEqual(vmux.remote_login("herdr status"), 'exec "$SHELL" -lc \'herdr status\'')

    def test_agent_list_formatting_matches_herdrs_reply(self):
        reply = {"id": "cli:agent:list", "result": {"type": "agent_list", "agents": [
            {"agent": "claude", "agent_status": "idle", "cwd": "/home/me/dev",
             "name": "claude-vmux-test", "pane_id": "w1:p1", "workspace_id": "w1"},
            {"agent": "codex", "agent_status": "working", "cwd": "/home/me/x",
             "name": None, "pane_id": "w2:p1", "workspace_id": "w2"},
        ]}}
        lines = vmux.format_herdr_agents(reply)
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^claude-vmux-test\s+claude\s+idle\s+/home/me/dev$")
        self.assertRegex(lines[1], r"^w2:p1\s+codex\s+working\s+/home/me/x$")
        self.assertEqual(len(vmux.format_herdr_agents({"result": {"agents": []}})), 1)

    def test_workspace_create_reply_yields_ids(self):
        reply = {"id": "cli:workspace:create", "result": {"type": "workspace_created",
                 "root_pane": {"pane_id": "w1:p1", "workspace_id": "w1", "tab_id": "w1:t1"},
                 "workspace": {"workspace_id": "w1", "label": "claude-x"}}}
        res = vmux.herdr_result(reply)
        self.assertEqual(vmux.herdr_id(res.get("root_pane"), "pane_id", "id"), "w1:p1")
        self.assertEqual(vmux.herdr_id(res.get("workspace"), "workspace_id", "id"), "w1")


if __name__ == "__main__":
    unittest.main()
