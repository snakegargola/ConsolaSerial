"""Dedicated GPIO session for one FTDI bridge interface."""

from PyQt6.QtCore import pyqtSignal

from .bridge_interface_manager import InterfaceBusyError
from .gpio_bus import gpio_width_for_interface, mask_for_width
from .gpio_widget import GpioPanel
from .gpio_worker import GpioWorker


class GpioSessionPanel(GpioPanel):
    """Own a channel in GPIO mode and run non-blocking pin operations."""

    worker_finished = pyqtSignal(object)

    def __init__(self, interface, bridge, config, channel_manager, parent=None):
        width = gpio_width_for_interface(bridge, interface)
        super().__init__(
            title=f"Dedicated GPIO — interface {interface.name}",
            width=width, available_mask=mask_for_width(width),
            pin_prefix=f"{interface.name}DBUS", parent=parent,
        )
        self.session_channel = interface.name
        self.session_interface = interface.index
        self.bound_bridge = bridge
        self.config = config
        self.channel_manager = channel_manager
        self._channel_owner = f"GPIO session {self.session_channel}"
        self._worker = None
        self._shutting_down = False
        self.apply_settings(config.get("gpio", {}))
        self.operation_requested.connect(self._run_operation)
        self.worker_finished.connect(self._operation_done)

    def activate_session(self):
        self._shutting_down = False
        try:
            self.channel_manager.acquire(
                self.session_channel, "GPIO", self._channel_owner
            )
            return True
        except InterfaceBusyError as exc:
            self.status.setText(f"ERROR: {exc}")
            return False

    def is_session_active(self):
        return bool(self._worker and self._worker.is_alive())

    def shutdown_session(self):
        self.config.set("gpio", self.settings_dict())
        self._shutting_down = True
        if not self.is_session_active():
            self.channel_manager.release(self.session_channel, self._channel_owner)

    def _run_operation(self, state, write_outputs):
        if self.is_session_active():
            return
        try:
            self.channel_manager.acquire(
                self.session_channel, "GPIO", self._channel_owner
            )
        except InterfaceBusyError as exc:
            self.status.setText(f"ERROR: {exc}")
            return
        self.set_busy(True)
        self.status.setText("Accessing physical GPIO pins…")
        url = f"{self.bound_bridge.base_url}/{self.session_interface}"
        self._worker = GpioWorker(
            url, state, self.worker_finished.emit,
            mpsse=bool(getattr(self._interface(), "has_mpsse", False)),
            write_outputs=write_outputs,
        )
        self._worker.start()

    def _interface(self):
        return next(
            item for item in self.bound_bridge.interfaces
            if item.index == self.session_interface
        )

    def _operation_done(self, result):
        self._worker = None
        self.set_busy(False)
        self.show_result(result)
        if self._shutting_down:
            self.channel_manager.release(self.session_channel, self._channel_owner)
