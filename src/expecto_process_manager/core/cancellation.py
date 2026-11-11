from threading import Event


class Cancelled(Exception):
    """Cooperative cancellation."""


class Cancellation:
    def __init__(self) -> None:
        self.event = Event()

    def cancel(self) -> None:
        self.event.set()

    def check(self) -> None:
        if self.event.is_set():
            raise Cancelled("Operação cancelada.")
