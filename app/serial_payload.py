"""Pure helpers for validating and encoding serial-console payloads."""


def parse_hex_payload(text):
    """Parse HEX digits separated by whitespace into bytes.

    Input is deliberately strict so the UI can promise that every visible
    pair is one transmitted byte. Prefixes such as ``0x`` and punctuation are
    rejected instead of being guessed.
    """
    source = str(text)
    invalid = next(
        (character for character in source if not character.isspace()
         and character not in "0123456789abcdefABCDEF"),
        None,
    )
    if invalid is not None:
        raise ValueError(
            f"HEX input contains an invalid character: {invalid!r}."
        )
    compact = "".join(source.split())
    if not compact:
        raise ValueError("Enter at least one HEX byte.")
    if len(compact) % 2:
        raise ValueError(
            "HEX input has an incomplete byte; use two digits per byte."
        )
    return bytes.fromhex(compact)


def encode_serial_payload(text, output_format, eol=b""):
    """Encode user input and append the exact configured line ending."""
    if not str(text):
        raise ValueError("Enter data to send.")
    if str(output_format).strip().upper() == "HEX":
        payload = parse_hex_payload(text)
    else:
        payload = str(text).encode("utf-8")
    return payload + bytes(eol)


def format_payload_preview(payload):
    """Return an unambiguous byte-for-byte HEX representation."""
    return bytes(payload).hex(" ").upper()
