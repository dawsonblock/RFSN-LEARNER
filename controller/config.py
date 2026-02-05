# controller/config.py
"""
Centralized configuration with environment variable fallbacks.

Controls test and shell execution modes (host vs docker).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class TestMode(Enum):
    """Execution environment mode."""

    HOST = "host"
    DOCKER = "docker"


@dataclass(frozen=True)
class DockerConfig:
    """Docker container configuration."""

    image: str = "python:3.12-slim"
    memory_limit: str = "2g"
    cpu_limit: float = 2.0
    network_disabled: bool = True
    workdir: str = "/workspace"


def get_test_mode() -> TestMode:
    """Get test execution mode from environment."""
    mode = os.getenv("RFSN_TEST_MODE", "host").lower()
    if mode == "docker":
        return TestMode.DOCKER
    return TestMode.HOST


def get_shell_mode() -> TestMode:
    """Get shell execution mode from environment."""
    mode = os.getenv("RFSN_SHELL_MODE", "host").lower()
    if mode == "docker":
        return TestMode.DOCKER
    return TestMode.HOST


def get_docker_config() -> DockerConfig:
    """Get Docker configuration from environment."""
    return DockerConfig(
        image=os.getenv("RFSN_DOCKER_IMAGE", "python:3.12-slim"),
        memory_limit=os.getenv("RFSN_DOCKER_MEMORY", "2g"),
        cpu_limit=float(os.getenv("RFSN_DOCKER_CPUS", "2.0")),
        network_disabled=os.getenv("RFSN_DOCKER_NETWORK", "disabled") == "disabled",
        workdir="/workspace",
    )


def use_docker() -> bool:
    """Convenience function: True if docker TEST mode is enabled."""
    return get_test_mode() == TestMode.DOCKER
