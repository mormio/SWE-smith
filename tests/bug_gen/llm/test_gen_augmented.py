def test_gen_augmented_returns_bugs(monkeypatch, tmp_path):
    from swesmith.bug_gen.augment.add_feature import gen_augmented
    from swesmith.constants import CodeEntity, BugRewrite

    class DummyEntity:
        """Minimal fake entity for testing gen_augmented."""
        def __init__(self):
            self.name = "foo"
            self.file_path = tmp_path / "f.py"
            self.file_path.write_text("def foo():\n    pass")
            self.line_start = 1
            self.line_end = 2
            self.indent_size = 4
            self.indent_level = 0


    dummy = DummyEntity()
    dummy_configs = {"system": "You are a helpful model.", "entity_instance": "Please modify {func_name}:\n{file_src_code}"}

    # mock litellm.completion
    monkeypatch.setattr(
        "swesmith.bug_gen.augment.add_feature.completion",
        lambda **_: type(
            "Resp", (),{
                "choices": [
                    type("C", (), {
                            "message": type("M", (), {"content": "```python\ndef foo():\n    return 1\n```"})()
                        },)
                ],
                "usage": {},
            },)()
    )

    monkeypatch.setattr("swesmith.bug_gen.augment.add_feature.completion_cost", lambda **_: 0.1)

    bugs = gen_augmented(dummy, dummy_configs, n_bugs=1, model="fake")
    assert isinstance(bugs[0], BugRewrite)
    assert "def foo" in bugs[0].rewrite
