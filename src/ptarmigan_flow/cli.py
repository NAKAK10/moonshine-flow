"""CLI compatibility alias.

Historically, all CLI helpers and command handlers lived in ``ptarmigan_flow.cli``.
The implementation now resides under ``ptarmigan_flow.presentation.cli.commands``.
This module keeps the old import path stable by aliasing that module object.
"""

from __future__ import annotations

import sys

from ptarmigan_flow.presentation.cli import commands as _commands

# Keep the historical module path as a live alias so monkeypatching and private
# helper access continue to affect the actual command implementation module.
sys.modules[__name__] = _commands
