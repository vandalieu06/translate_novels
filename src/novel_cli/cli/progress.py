"""Progreso con rich (solo CLI; core nunca importa rich)."""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)


class ProgressUI:
    """Barras de descarga/traduccion/EPUB conectadas a los callbacks de core."""

    def __init__(self, *, verbose: bool = False):
        self.verbose = verbose
        self.console = Console(stderr=True, highlight=False)
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._tasks: dict[str, TaskID] = {}

    def __enter__(self) -> ProgressUI:
        self.progress.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.progress.stop()

    def status(self, message: str) -> None:
        self.console.print(message)

    def callback(self, key: str, description: str) -> Callable[[int, int], None]:
        """Devuelve un on_progress que crea la barra de forma perezosa."""

        def handler(done: int, total: int) -> None:
            if key not in self._tasks:
                self._tasks[key] = self.progress.add_task(description, total=total)
            self.progress.update(self._tasks[key], completed=done, total=total)

        return handler