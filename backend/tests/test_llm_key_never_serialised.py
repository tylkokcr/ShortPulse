"""The server's OpenAI key must never leave the process inside a project."""

from __future__ import annotations

from app.schemas.project import LLMConfig, Project, ProjectConfig


def test_the_key_is_left_out_of_every_dump():
    config = ProjectConfig(topic="x", llm=LLMConfig(provider="openai", api_key="sk-secret"))
    project = Project(config=config)

    assert "sk-secret" not in config.model_dump_json()
    assert "sk-secret" not in project.model_dump_json()
    assert "api_key" not in project.model_dump(mode="json")["config"]["llm"]
    # Still usable in memory, where script_engine reads it.
    assert config.llm.api_key == "sk-secret"


def test_a_config_read_back_has_no_key():
    stored = ProjectConfig(topic="x", llm=LLMConfig(provider="openai", api_key="sk-secret")).model_dump_json()
    assert ProjectConfig.model_validate_json(stored).llm.api_key is None
