#!/usr/bin/env python3
"""
Legacy OpenClaw wrapper.

Project launch workflows now run through CodeMonkeyClaw so there is one control
plane for operator automation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print('usage: python3 project-launch.py <project_name> [description]')
        sys.exit(1)

    project = sys.argv[1]
    description = " ".join(sys.argv[2:]).strip()

    codemonkey = Path.home() / "code" / "claw-platform" / "codemonkeyclaw"
    run_py = codemonkey / "run.py"
    python = codemonkey / ".venv" / "bin" / "python"
    params = json.dumps({"project": project, "description": description})

    cmd = [str(python), str(run_py), "workflow", "--chat-id", "openclaw-project-launch", "--name", "project-launch", "--params", params]
    result = subprocess.run(cmd, cwd=str(codemonkey), text=True, capture_output=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
