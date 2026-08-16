"""Compatibility layer for the former FT4232-specific manager module."""

from .bridge_interface_manager import (
    InterfaceBusyError as ChannelBusyError,
    UsbBridgeInterfaceManager,
)


CHANNEL_CAPABILITIES = {
    "A": frozenset({"UART", "I2C", "SPI", "JTAG", "GPIO"}),
    "B": frozenset({"UART", "I2C", "SPI", "JTAG", "GPIO"}),
    "C": frozenset({"UART"}),
    "D": frozenset({"UART"}),
}


class FtdiChannelManager(UsbBridgeInterfaceManager):
    """Legacy constructor that defaults to the FT4232 interface layout."""

    def __init__(self, modes=None, capabilities=None):
        super().__init__(
            modes=modes,
            capabilities=(
                CHANNEL_CAPABILITIES if capabilities is None else capabilities
            ),
        )
