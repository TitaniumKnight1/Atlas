from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request

from backend.infrastructure.di import ApplicationContainer
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


def get_unit_of_work(
    container: ApplicationContainer = Depends(get_container),
) -> Iterator[SingleWriterSQLiteUnitOfWork]:
    with container.create_unit_of_work() as unit_of_work:
        yield unit_of_work
