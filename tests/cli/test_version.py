from forge import __version__
from forge.cli import build_parser, main


def test_version_is_initial_development_release() -> None:
    assert __version__ == "0.1.0.dev0"


def test_parser_uses_forge_program_name() -> None:
    assert build_parser().prog == "forge"


def test_version_flag_prints_version(capsys) -> None:
    exit_code = main(["--version"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "forge 0.1.0.dev0\n"
    assert captured.err == ""
