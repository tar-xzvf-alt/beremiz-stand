#!/usr/bin/env python3
import argparse
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _cmd
from _lib import load_profile


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_profile(ROOT / "profiles" / "stand.conf.example")

    def run_doctor(self, required_tools_available=True):
        def tool_available(name):
            if name in {"prometheus", "/bin/prometheus", "grafana-server"}:
                return False
            return required_tools_available

        def path_exists(path):
            return path != Path("/bin/grafana-server")

        output = io.StringIO()
        with (
            mock.patch.object(_cmd, "check_local_tool", side_effect=tool_available),
            mock.patch.object(_cmd, "check_path", side_effect=path_exists),
            mock.patch.object(_cmd, "ssh_check", return_value=(True, "")),
            mock.patch.object(_cmd, "ssh_jump_check", return_value=(True, "")),
            mock.patch.object(_cmd, "http_check", return_value=False),
            contextlib.redirect_stdout(output),
        ):
            result = _cmd.cmd_doctor(self.cfg, argparse.Namespace())
        return result, output.getvalue()

    def test_optional_services_are_warnings_and_do_not_fail(self):
        result, output = self.run_doctor()

        self.assertEqual(result, 0)
        self.assertIn("[WARN] prometheus in PATH or /bin/prometheus", output)
        self.assertIn("[WARN] grafana-server in PATH or /bin/grafana-server", output)
        self.assertIn("[WARN] trace Prometheus ready:", output)
        self.assertIn("[WARN] trace Grafana ready:", output)
        self.assertNotIn("[FAIL] prometheus", output)
        self.assertNotIn("[FAIL] grafana", output)
        self.assertIn("Doctor passed", output)

    def test_required_tool_still_fails_doctor(self):
        result, output = self.run_doctor(required_tools_available=False)

        self.assertEqual(result, 1)
        self.assertIn("[FAIL] python3 in PATH", output)
        self.assertIn("Doctor found 4 problem(s)", output)


if __name__ == "__main__":
    unittest.main()
