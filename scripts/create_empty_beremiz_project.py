#!/usr/bin/env python3
"""Create an empty Beremiz project with the system Beremiz package."""

import argparse
import os
import sys


BEREMIZ_MODULE_PATH = "/usr/share/beremiz"


def parse_args():
	parser = argparse.ArgumentParser(description="Create an empty Beremiz project")
	parser.add_argument("project_dir", help="empty directory where project is created")
	return parser.parse_args()


def main():
	args = parse_args()
	project_dir = os.path.abspath(args.project_dir)

	if not os.path.isdir(BEREMIZ_MODULE_PATH):
		print(f"Beremiz module path not found: {BEREMIZ_MODULE_PATH}", file=sys.stderr)
		return 1

	os.makedirs(project_dir, exist_ok=True)
	if os.listdir(project_dir):
		print(f"Project directory is not empty: {project_dir}", file=sys.stderr)
		return 1

	sys.path.insert(0, BEREMIZ_MODULE_PATH)
	import fake_wx  # noqa: F401  # Beremiz CLI mode without GUI dialogs.
	from ProjectController import ProjectController

	controller = ProjectController()
	error = controller.NewProject(project_dir)
	if error is not None:
		print(error, file=sys.stderr)
		return 1

	print(f"Created Beremiz project: {project_dir}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
