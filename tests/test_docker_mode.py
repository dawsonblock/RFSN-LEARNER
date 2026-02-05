# tests/test_docker_mode.py
"""Tests for Docker mode configuration and switching."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from controller.config import (
    DockerConfig,
    TestMode,
    get_docker_config,
    get_test_mode,
    use_docker,
)
from controller.docker_runner import run_pytest_in_docker


class TestConfigModule:
    """Tests for configuration parsing."""

    def test_default_mode_is_host(self):
        """Default test mode should be host."""
        with patch.dict(os.environ, {}, clear=True):
            mode = get_test_mode()
        assert mode == TestMode.HOST

    def test_docker_mode_from_env(self):
        """RFSN_TEST_MODE=docker should enable docker mode."""
        with patch.dict(os.environ, {"RFSN_TEST_MODE": "docker"}):
            mode = get_test_mode()
        assert mode == TestMode.DOCKER

    def test_docker_mode_case_insensitive(self):
        """Mode detection should be case-insensitive."""
        with patch.dict(os.environ, {"RFSN_TEST_MODE": "DOCKER"}):
            mode = get_test_mode()
        assert mode == TestMode.DOCKER

    def test_invalid_mode_defaults_to_host(self):
        """Invalid mode values should default to host."""
        with patch.dict(os.environ, {"RFSN_TEST_MODE": "invalid"}):
            mode = get_test_mode()
        assert mode == TestMode.HOST

    def test_use_docker_helper(self):
        """use_docker() should return True for docker mode."""
        with patch.dict(os.environ, {"RFSN_TEST_MODE": "docker"}):
            assert use_docker() is True

        with patch.dict(os.environ, {"RFSN_TEST_MODE": "host"}):
            assert use_docker() is False


class TestDockerConfig:
    """Tests for Docker configuration."""

    def test_default_config(self):
        """Default Docker config should have reasonable values."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_docker_config()
        assert config.image == "python:3.12-slim"
        assert config.memory_limit == "2g"
        assert config.cpu_limit == 2.0
        assert config.network_disabled is True

    def test_custom_image_from_env(self):
        """Custom docker image should be read from env."""
        with patch.dict(os.environ, {"RFSN_DOCKER_IMAGE": "python:3.11"}):
            config = get_docker_config()
        assert config.image == "python:3.11"

    def test_custom_memory_from_env(self):
        """Custom memory limit should be read from env."""
        with patch.dict(os.environ, {"RFSN_DOCKER_MEMORY": "4g"}):
            config = get_docker_config()
        assert config.memory_limit == "4g"

    def test_custom_cpus_from_env(self):
        """Custom CPU limit should be read from env."""
        with patch.dict(os.environ, {"RFSN_DOCKER_CPUS": "4.0"}):
            config = get_docker_config()
        assert config.cpu_limit == 4.0


class TestRunPytestInDocker:
    """Tests for the run_pytest_in_docker adapter."""

    def test_result_structure(self, tmp_path: Path):
        """Result should have kernel-compatible structure."""
        # Create minimal test file
        test_file = tmp_path / "test_example.py"
        test_file.write_text("def test_pass(): pass")

        # Mock run_in_container to avoid actual Docker
        from controller.docker_runner import ContainerResult

        mock_result = ContainerResult(
            exit_code=0,
            stdout="1 passed in 0.01s",
            stderr="",
            timed_out=False,
        )

        with patch("controller.docker_runner.run_in_container", return_value=mock_result):
            result = run_pytest_in_docker(tmp_path)

        assert "returncode" in result
        assert "stdout" in result
        assert "stderr" in result
        assert "meta" in result
        assert result["meta"]["docker"] is True

    def test_timeout_metadata(self, tmp_path: Path):
        """Timeout should be captured in metadata."""
        from controller.docker_runner import ContainerResult

        mock_result = ContainerResult(
            exit_code=-1,
            stdout="",
            stderr="Container execution timed out",
            timed_out=True,
        )

        with patch("controller.docker_runner.run_in_container", return_value=mock_result):
            result = run_pytest_in_docker(tmp_path, timeout_seconds=5)

        assert result["meta"]["timed_out"] is True
        assert result["returncode"] == -1
