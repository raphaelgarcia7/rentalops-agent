import copy
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from infra.operations import runtime

from rentalops_api.operations import OperationsError


@pytest.fixture
def host_configuration(tmp_path, monkeypatch):
    for name in [*runtime.PATHS, "LOCAL_PORT"]:
        monkeypatch.delenv(name, raising=False)
    paths = {}
    for name, directory in runtime.PATHS.items():
        path = tmp_path / name.lower()
        if directory:
            path.mkdir(mode=0o700)
        else:
            path.write_text("SYNTHETIC_PRIVATE_SENTINEL\n")
            path.chmod(0o600)
        paths[name] = path
    env_file = tmp_path / "compose.env"
    env_file.write_text(
        "\n".join(f"{name}={path.as_posix()}" for name, path in paths.items())
    )
    env_file.chmod(0o600)
    return env_file, paths


def model_for(paths):
    return {
        "services": {
            name: {
                "volumes": [
                    {"type": "bind", "source": str(paths[key]), "target": target}
                    for target, key in expected.items()
                ]
            }
            for name, expected in runtime.BINDS.items()
        }
        | {
            "backend": {
                "volumes": [
                    {"type": "bind", "source": str(paths[key]), "target": target}
                    for target, key in runtime.BINDS["backend"].items()
                ],
                "env_file": [{"path": str(paths["BACKEND_ENV_FILE"])}],
            }
        },
        "secrets": {
            "postgres_password": {"file": str(paths["POSTGRES_PASSWORD_FILE"])}
        },
    }


@pytest.mark.parametrize("name", runtime.PATHS)
@pytest.mark.parametrize("value", ["./relative-data", "relative-data", ""])
@pytest.mark.parametrize("action", ["validate", "build", "up"])
def test_raw_relative_or_empty_paths_refused_before_docker(
    host_configuration, monkeypatch, name, value, action
):
    env_file, _ = host_configuration
    monkeypatch.setenv(name, value)
    with patch.object(runtime, "compose_command") as command:
        with pytest.raises(OperationsError):
            runtime.run(action, env_file, "rentalops-synthetic-test")
        command.assert_not_called()


def test_git_public_missing_wrong_type_overlap_and_secret_in_volume_refused(
    host_configuration, tmp_path, monkeypatch
):
    env_file, paths = host_configuration
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    (repository / ".git").write_text("synthetic git marker")
    git_volume = repository / "photos"
    git_volume.mkdir(mode=0o700)
    public = tmp_path / "Public"
    public.mkdir(mode=0o700)
    nested = paths["OPERATIONS_VOLUME"] / "nested"
    nested.mkdir(mode=0o700)
    for value in [
        git_volume,
        public,
        tmp_path / "missing",
        paths["BACKEND_ENV_FILE"],
        paths["OPERATIONS_VOLUME"],
        nested,
    ]:
        monkeypatch.setenv("STORAGE_VOLUME", str(value))
        with pytest.raises(OperationsError):
            runtime.configuration(env_file)
    monkeypatch.delenv("STORAGE_VOLUME")
    secret = paths["STORAGE_VOLUME"] / "secret.env"
    secret.write_text("synthetic")
    secret.chmod(0o600)
    monkeypatch.setenv("BACKEND_ENV_FILE", str(secret))
    with pytest.raises(OperationsError):
        runtime.configuration(env_file)


def test_actual_junction_or_symlink_refused(host_configuration, tmp_path, monkeypatch):
    env_file, paths = host_configuration
    linked = tmp_path / "linked"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(paths["STORAGE_VOLUME"]), str(linked))
    else:
        linked.symlink_to(paths["STORAGE_VOLUME"], target_is_directory=True)
    monkeypatch.setenv("STORAGE_VOLUME", str(linked))
    with pytest.raises(OperationsError):
        runtime.configuration(env_file)
    assert linked.is_symlink() or linked.is_junction()
    assert paths["STORAGE_VOLUME"].is_dir()


@pytest.mark.parametrize("name", runtime.PATHS)
def test_actual_public_permissions_refused(host_configuration, monkeypatch, name):
    env_file, paths = host_configuration
    path = paths[name]
    if os.name == "nt":
        subprocess.run(
            ["icacls", str(path), "/grant", "*S-1-1-0:(R)"],
            check=True,
            capture_output=True,
        )
    else:
        path.chmod(0o755 if path.is_dir() else 0o644)
    try:
        with pytest.raises(OperationsError):
            runtime.configuration(env_file)
    finally:
        if os.name == "nt":
            subprocess.run(
                ["icacls", str(path), "/remove:g", "*S-1-1-0"],
                check=True,
                capture_output=True,
            )
        else:
            path.chmod(0o700 if path.is_dir() else 0o600)


@pytest.mark.parametrize(
    "mutation", ["source", "target", "type", "extra", "env", "secret"]
)
def test_resolved_compose_mismatch_blocks_build_and_up(host_configuration, mutation):
    env_file, paths = host_configuration
    model = model_for(paths)
    backend = model["services"]["backend"]
    if mutation == "source":
        backend["volumes"][0]["source"] = str(paths["DATABASE_VOLUME"])
    elif mutation == "target":
        backend["volumes"][0]["target"] = "/public/photos"
    elif mutation == "type":
        backend["volumes"][0]["type"] = "volume"
    elif mutation == "extra":
        backend["volumes"].append(copy.deepcopy(backend["volumes"][0]))
    elif mutation == "env":
        backend["env_file"][0]["path"] = str(paths["POSTGRES_PASSWORD_FILE"])
    else:
        model["secrets"]["postgres_password"]["file"] = str(paths["BACKEND_ENV_FILE"])
    for action in ["build", "up"]:
        with patch.object(
            runtime, "compose_command", return_value=json.dumps(model)
        ) as command:
            with pytest.raises(OperationsError):
                runtime.run(action, env_file, "rentalops-synthetic-test")
            assert command.call_count == 1
            assert "config" in command.call_args.args[0]


@pytest.mark.parametrize("action", ["build", "up"])
def test_mutation_requires_validated_host_and_resolved_sources(
    host_configuration, action
):
    env_file, paths = host_configuration
    with patch.object(
        runtime, "compose_command", return_value=json.dumps(model_for(paths))
    ) as command:
        runtime.run(action, env_file, "rentalops-synthetic-test")
        assert command.call_count == 2
        first, second = command.call_args_list
        assert first.args[0][-4:] == [
            "config",
            "--format",
            "json",
            "--no-env-resolution",
        ]
        assert action in second.args[0]
        if action == "up":
            assert second.args[0][-4:] == [
                "--detach",
                "--wait",
                "--wait-timeout",
                "120",
            ]


def test_real_compose_resolution_and_safe_cli_errors(host_configuration, capsys):
    env_file, _ = host_configuration
    # Real installed Compose parser; requires no engine and starts no resources.
    runtime.run("validate", env_file, "rentalops-synthetic-test")
    with (
        patch(
            "sys.argv",
            [
                "runtime",
                "build",
                "--env-file",
                str(env_file),
                "--project",
                "rentalops-synthetic-test",
            ],
        ),
        patch.object(
            runtime,
            "compose_command",
            side_effect=OSError("SYNTHETIC_PRIVATE_SENTINEL"),
        ),
    ):
        assert runtime.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "failed", "category": "host_preparation"}
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in output and str(env_file) not in output


def test_private_external_compose_env_required(host_configuration, tmp_path):
    env_file, _ = host_configuration
    for path in [Path("compose.env"), tmp_path / "missing.env", tmp_path]:
        with pytest.raises(OperationsError):
            runtime.configuration(path)
    (tmp_path / ".git").write_text("synthetic git marker")
    with pytest.raises(OperationsError):
        runtime.configuration(env_file)
