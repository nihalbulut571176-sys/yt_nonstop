# Testing

Primary test runner:

```bash
python -m pytest -q tests/test_v2_pipeline.py::V2PipelineTests::test_v2_pipeline_cli_builds_and_exports
python -m pytest -q
```

`unittest` remains compatible for direct module runs, but `pytest` is the supported default for contributor and CI-style reproduction.
