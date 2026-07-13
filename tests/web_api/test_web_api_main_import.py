import importlib


def test_web_api_main_imports_with_runtime_finalizer_dependencies():
    module = importlib.import_module("src.web_api.main")

    assert module.app is not None
