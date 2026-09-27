"""Offline source parsers; expected upstream failures use ParseError."""


class ParseError(ValueError):
    """The source cannot be parsed as a complete, structurally valid result."""
