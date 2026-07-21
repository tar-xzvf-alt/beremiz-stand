#!/usr/bin/env python3
import argparse
import configparser
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _cmd
from _lib import load_profile


class SourceFlowTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_profile(ROOT / "profiles" / "rockpi-visionfive.conf")

    def test_profiles_use_split_source_trees_and_runtime_boards(self):
        for path in sorted((ROOT / "profiles").glob("*.conf")):
            cfg = load_profile(path)
            self.assertTrue(cfg.get("pc", "rt_controller_dir"), path)
            self.assertTrue(cfg.get("controller", "rt_controller_dir"), path)
            self.assertNotIn("rt-supervisor", cfg.get("controller", "controller_bin"), path)
            self.assertNotIn(cfg.get("controller", "board"), {"starfive", "repkapi4"}, path)

    def test_controller_build_uses_own_tree_without_board_cache(self):
        command = _cmd.cmake_build_command(
            "/root/rt-controller", "controller-emu", True)

        self.assertIn("cd /root/rt-controller", command)
        self.assertIn("--target controller-emu --clean-first", command)
        self.assertNotIn("-DBOARD", command)

    def test_deploy_routes_each_archive_to_its_role(self):
        args = argparse.Namespace(
            supervisor_only=False,
            controller_only=False,
            dry_run=False,
        )
        archives = [Path("/tmp/missing-supervisor.tgz"), Path("/tmp/missing-controller.tgz")]
        with (
            mock.patch.object(_cmd, "create_source_archive", side_effect=archives),
            mock.patch.object(_cmd, "deploy_archive") as deploy,
        ):
            _cmd.cmd_deploy_rt_supervisor(self.cfg, args)

        self.assertEqual(deploy.call_count, 2)
        self.assertEqual(deploy.call_args_list[0].args[1:4], (
            "/root/rt-supervisor", archives[0], "rt-supervisor"))
        self.assertEqual(deploy.call_args_list[1].args[1:4], (
            "/root/rt-controller", archives[1], "rt-controller"))

    def test_start_uses_controller_board_tree_exporter_and_barrier(self):
        with (
            mock.patch.object(_cmd, "cmd_stop"),
            mock.patch.object(_cmd, "_ssh_script_args", return_value=(True, "")) as supervisor_start,
            mock.patch.object(_cmd, "ssh_jump_script", return_value=(True, "")) as controller_start,
            mock.patch.object(_cmd, "ssh_check", return_value=(True, "")),
            mock.patch.object(_cmd, "ssh_jump_check", return_value=(True, "")),
            mock.patch.object(_cmd.time, "sleep"),
        ):
            _cmd._start_stack(
                self.cfg,
                trace_session_id="123",
                trace_mpg="100",
                trace_exporters=True,
                controller_paused=True,
                trace_groups="2",
            )

        supervisor_args = supervisor_start.call_args.args[2]
        controller_args = controller_start.call_args.kwargs["shell_args"]
        self.assertIn("/root/rt-supervisor/scripts/run_supervisor.sh", supervisor_args)
        self.assertEqual(controller_args[1:3], ["end0", "visionfive2"])
        self.assertIn("/root/rt-controller/scripts/run_controller.sh", controller_args)
        self.assertIn("/root/rt-controller/scripts/trace_exporter.py", controller_args)
        self.assertEqual(controller_args[-2:], ["1", "2"])

    def test_check_propagates_missing_controller(self):
        with (
            mock.patch.object(_cmd, "ssh_check", return_value=(True, "PLC Status: Started")),
            mock.patch.object(_cmd, "ssh_script", return_value=(True, "supervisor ok")),
            mock.patch.object(_cmd, "ssh_jump_script", return_value=(False, "controller missing")),
        ):
            result = _cmd.cmd_check(self.cfg, argparse.Namespace())

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
