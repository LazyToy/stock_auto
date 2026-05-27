import tomllib
from pathlib import Path


def test_automl_runtime_dependency_deap_is_declared():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert any(dependency.lower().startswith("deap") for dependency in dependencies)
