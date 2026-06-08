from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

import click
from agentlens_client.errors import (
    AgentLensClientError,
    BackendBusinessError,
    BackendServerError,
    BackendUnavailableError,
)

P = ParamSpec("P")
R = TypeVar("R")


class AgentLensCliError(click.ClickException):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def handle_errors(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except AgentLensCliError:
            raise
        except BackendUnavailableError as exc:
            raise AgentLensCliError(str(exc), exit_code=3) from exc
        except BackendBusinessError as exc:
            raise AgentLensCliError(str(exc), exit_code=4) from exc
        except BackendServerError as exc:
            raise AgentLensCliError(str(exc), exit_code=5) from exc
        except AgentLensClientError as exc:
            raise AgentLensCliError(str(exc), exit_code=1) from exc

    return wrapper
