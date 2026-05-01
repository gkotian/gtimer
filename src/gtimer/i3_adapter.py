from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

import i3ipc
from i3ipc import Event

from .models import WindowInfo


FocusCallback = Callable[[WindowInfo | None], None]
StatusCallback = Callable[[bool, str | None], None]


class I3FocusAdapter:
    def __init__(self, on_focus: FocusCallback, on_status: StatusCallback) -> None:
        self.on_focus = on_focus
        self.on_status = on_status
        self.connection: i3ipc.Connection | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="gtimer-i3", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.connection is not None:
            self.connection.main_quit()

    def _run(self) -> None:
        try:
            connection = i3ipc.Connection()
            self.connection = connection
            self.on_status(True, None)

            focused = connection.get_tree().find_focused()
            self.on_focus(_window_from_i3(focused))

            connection.on(Event.WINDOW_FOCUS, self._handle_focus)
            connection.main()
        except Exception as error:
            self.on_status(False, str(error))

    def _handle_focus(self, _connection: i3ipc.Connection, event: Any) -> None:
        self.on_focus(_window_from_i3(event.container))


def _window_from_i3(container: Any) -> WindowInfo | None:
    if container is None:
        return None
    title = getattr(container, "name", None) or ""
    window_class = getattr(container, "window_class", None)
    instance = getattr(container, "window_instance", None)
    if not title and not window_class and not instance:
        return None
    return WindowInfo(title=title, window_class=window_class, instance=instance)
