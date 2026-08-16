"""Thread-safe mode and ownership tracking for USB bridge interfaces."""

from threading import RLock


class InterfaceBusyError(RuntimeError):
    """Raised when a mode or owner conflicts with an active interface."""


class UsbBridgeInterfaceManager:
    """Track one mode and at most one owner for each adapter interface."""

    def __init__(self, modes=None, capabilities=None):
        requested = modes or {}
        self._capabilities = {
            str(name).upper(): frozenset(protocols)
            for name, protocols in (capabilities or {}).items()
        }
        self._modes = {
            name: self._validate_mode(name, requested.get(name, "UART"))
            for name in self._capabilities
        }
        self._owners = {name: None for name in self._capabilities}
        self._lock = RLock()

    def _validate_mode(self, interface, mode):
        interface = str(interface).upper()
        mode = str(mode).upper()
        if interface not in self._capabilities:
            raise ValueError(f"Unknown adapter interface: {interface}")
        if mode not in self._capabilities[interface]:
            supported = ", ".join(sorted(self._capabilities[interface]))
            raise ValueError(f"Interface {interface} supports: {supported}.")
        return mode

    def capabilities(self, interface):
        return self._capabilities[str(interface).upper()]

    def mode(self, interface):
        with self._lock:
            return self._modes[str(interface).upper()]

    def owner(self, interface):
        with self._lock:
            return self._owners[str(interface).upper()]

    def set_mode(self, interface, mode):
        interface = str(interface).upper()
        mode = self._validate_mode(interface, mode)
        with self._lock:
            owner = self._owners[interface]
            if owner is not None and mode != self._modes[interface]:
                raise InterfaceBusyError(
                    f"Interface {interface} is active in "
                    f"{self._modes[interface]} mode."
                )
            self._modes[interface] = mode

    def acquire(self, interface, mode, owner):
        interface = str(interface).upper()
        mode = self._validate_mode(interface, mode)
        if not owner:
            raise ValueError("Interface owner cannot be empty.")
        with self._lock:
            if self._modes[interface] != mode:
                raise InterfaceBusyError(
                    f"Interface {interface} is assigned to "
                    f"{self._modes[interface]}, not {mode}."
                )
            current = self._owners[interface]
            if current not in (None, owner):
                raise InterfaceBusyError(
                    f"Interface {interface} is already used by {current}."
                )
            self._owners[interface] = owner

    def release(self, interface, owner):
        interface = str(interface).upper()
        with self._lock:
            if self._owners[interface] == owner:
                self._owners[interface] = None

    def snapshot(self):
        with self._lock:
            return {
                interface: {
                    "mode": self._modes[interface],
                    "owner": self._owners[interface],
                }
                for interface in self._capabilities
            }
