"""Read files from the public em-macro repository: a local checkout when EM_MACRO_DIR is set,
otherwise raw.githubusercontent.com. Results are cached for the life of the process."""

from __future__ import annotations

import functools
import io
import os
from pathlib import Path

import pandas as pd

from terminal.http import get

RAW = "https://raw.githubusercontent.com/EthanC100/em-macro/main/"


@functools.lru_cache(maxsize=None)
def text(path: str) -> str:
    local = os.environ.get("EM_MACRO_DIR")
    if local and (Path(local) / path).exists():
        return (Path(local) / path).read_text()
    return get(RAW + path, timeout=90).text


def frame(path: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text(path)))


def url(path: str) -> str:
    return RAW.replace("raw.githubusercontent.com", "github.com").replace("/main/", "/blob/main/") + path
