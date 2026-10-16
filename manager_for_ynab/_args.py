from __future__ import annotations

import argparse


def nonempty(raw: str) -> str:
    if not raw.strip():
        raise argparse.ArgumentTypeError("must not be empty")
    return raw


__all__ = ["nonempty"]
