from __future__ import annotations

from pathlib import Path

import pytest

from sensegnat.cli import main


def _write_config(tmp_path: Path, adapter_section: str = "adapter:\n  type: sample\n") -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        adapter_section
        + "storage:\n"
        + f"  profile_store_path: {tmp_path / 'profiles.json'}\n"
        + f"  finding_store_path: {tmp_path / 'findings.json'}\n"
    )
    return path


class TestCliRun:
    def test_run_once_exits_zero_and_prints_summary(self, tmp_path: Path, capsys) -> None:
        config = _write_config(tmp_path)

        exit_code = main(["run", "--config", str(config)])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "published" in out
        assert "STIX objects" in out

    def test_baseline_persists_across_cli_invocations(self, tmp_path: Path, capsys) -> None:
        # The sample adapter emits the same destination every run and the
        # config has no policy, so once the JSON-backed baseline exists the
        # second invocation publishes nothing.
        config = _write_config(tmp_path)
        main(["run", "--config", str(config)])
        capsys.readouterr()

        exit_code = main(["run", "--config", str(config)])
        assert exit_code == 0
        assert "published 0 STIX objects" in capsys.readouterr().out

    def test_missing_adapter_section_exits_2(self, tmp_path: Path, capsys) -> None:
        config = _write_config(tmp_path, adapter_section="")

        exit_code = main(["run", "--config", str(config)])

        assert exit_code == 2
        assert "no 'adapter:' section" in capsys.readouterr().err

    def test_missing_config_file_exits_2(self, tmp_path: Path, capsys) -> None:
        exit_code = main(["run", "--config", str(tmp_path / "nope.yaml")])

        assert exit_code == 2
        assert "error:" in capsys.readouterr().err

    def test_bad_adapter_type_exits_2(self, tmp_path: Path, capsys) -> None:
        config = _write_config(tmp_path, adapter_section="adapter:\n  type: netcat\n")

        exit_code = main(["run", "--config", str(config)])

        assert exit_code == 2
        assert "unknown adapter type" in capsys.readouterr().err


class TestCliVersion:
    def test_version_flag_prints_version(self, capsys) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])

        assert excinfo.value.code == 0
        assert "sensegnat" in capsys.readouterr().out

    def test_no_command_exits_nonzero(self, capsys) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([])

        assert excinfo.value.code != 0
