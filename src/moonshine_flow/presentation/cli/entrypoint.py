"""CLI entrypoint."""

from __future__ import annotations

from moonshine_flow.presentation.cli import commands
from moonshine_flow.presentation.cli.parser import build_parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


__all__ = ["build_parser", "main", "commands"]
