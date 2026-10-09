"""Host-side, fail-closed entry point for the approved Compose preparation."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from rentalops_api.operations import OperationsError, private_path

COMPOSE = Path(__file__).resolve().with_name("compose.yaml")
PATHS = {
    "DATABASE_VOLUME": True,
    "STORAGE_VOLUME": True,
    "OPERATIONS_VOLUME": True,
    "BACKEND_ENV_FILE": False,
    "POSTGRES_PASSWORD_FILE": False,
}
BINDS = {
    "database": {"/var/lib/postgresql/data": "DATABASE_VOLUME"},
    "backend": {
        "/private/photos": "STORAGE_VOLUME",
        "/private/operations": "OPERATIONS_VOLUME",
    },
    "frontend": {},
}


def host_path(value: str, *, directory: bool) -> Path:
    # Do not resolve first: that would disguise relative paths and reparse points.
    path = Path(value)
    if (
        not value
        or not path.is_absolute()
        or path == Path(path.anchor)
        or any(part.casefold() in {"public", "www", "htdocs"} for part in path.parts)
    ):
        raise OperationsError("Unsafe host configuration.")
    private_path(path, directory=directory)
    # The containing private root must not let other users replace the entry.
    private_path(path.parent)
    return path


def configuration(env_file: Path) -> tuple[dict[str, str], dict[str, Path]]:
    host_path(str(env_file), directory=False)
    values = dotenv_values(env_file, interpolate=False)
    environment = os.environ.copy()
    paths: dict[str, Path] = {}
    for name, directory in PATHS.items():
        value = os.environ.get(name, values.get(name))
        if not isinstance(value, str):
            raise OperationsError("Unsafe host configuration.")
        paths[name] = host_path(value, directory=directory)
        environment[name] = value
    roots = [paths[name] for name, directory in PATHS.items() if directory]
    for index, first in enumerate(roots):
        for second in roots[index + 1 :]:
            if first.is_relative_to(second) or second.is_relative_to(first):
                raise OperationsError("Host volumes must be independent.")
    for path in [
        env_file,
        *(paths[n] for n, directory in PATHS.items() if not directory),
    ]:
        if any(path.is_relative_to(root) for root in roots):
            raise OperationsError("Unsafe host configuration.")
    environment["LOCAL_PORT"] = os.environ.get(
        "LOCAL_PORT", values.get("LOCAL_PORT") or "8080"
    )
    return environment, paths


def resolved_configuration(model: dict[str, Any], paths: dict[str, Path]) -> None:
    """Check Compose's resolved sources, not container-side /private aliases."""
    services = model["services"]
    if set(services) != set(BINDS):
        raise OperationsError("Unexpected Compose configuration.")
    for name, expected in BINDS.items():
        volumes = services[name].get("volumes", [])
        if len(volumes) != len(expected):
            raise OperationsError("Unexpected Compose configuration.")
        actual: dict[str, Path] = {}
        for volume in volumes:
            if volume["type"] != "bind" or volume["target"] in actual:
                raise OperationsError("Unexpected Compose configuration.")
            actual[volume["target"]] = host_path(volume["source"], directory=True)
        if actual != {target: paths[key] for target, key in expected.items()}:
            raise OperationsError("Unexpected Compose configuration.")
    env_files = services["backend"]["env_file"]
    if (
        len(env_files) != 1
        or host_path(env_files[0]["path"], directory=False) != paths["BACKEND_ENV_FILE"]
    ):
        raise OperationsError("Unexpected Compose configuration.")
    secrets = model["secrets"]
    if (
        set(secrets) != {"postgres_password"}
        or host_path(secrets["postgres_password"]["file"], directory=False)
        != paths["POSTGRES_PASSWORD_FILE"]
    ):
        raise OperationsError("Unexpected Compose configuration.")


def compose_command(command: list[str], environment: dict[str, str]) -> str:
    result = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    # Compose diagnostics/build output may contain private host paths or env values.
    if result.returncode:
        raise OperationsError("Compose preparation failed.")
    return result.stdout


def run(action: str, env_file: Path, project: str) -> None:
    if action not in {"validate", "build", "up"} or not re.fullmatch(
        r"rentalops-[a-z0-9][a-z0-9-]{1,48}", project
    ):
        raise OperationsError("Invalid preparation command.")
    environment, paths = configuration(env_file)
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env_file),
        "--file",
        str(COMPOSE),
    ]
    model = json.loads(
        compose_command(
            [*command, "config", "--format", "json", "--no-env-resolution"], environment
        )
    )
    resolved_configuration(model, paths)
    if action != "validate":
        # Recheck immediately before mutation; never automatically chmod/create paths.
        current_environment, current_paths = configuration(env_file)
        if current_paths != paths or current_environment != environment:
            raise OperationsError("Host configuration changed.")
        compose_command(
            [
                *command,
                *(
                    ["build"]
                    if action == "build"
                    else ["up", "--detach", "--wait", "--wait-timeout", "120"]
                ),
            ],
            environment,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate", "build", "up"])
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        run(args.action, args.env_file, args.project)
    except (
        OperationsError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ):
        print(json.dumps({"status": "failed", "category": "host_preparation"}))
        return 1
    print(json.dumps({"status": "ok", "operation": args.action}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
