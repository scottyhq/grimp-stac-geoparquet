"""Shared configuration for the GRIMP staging demo."""

import os
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SHORT_NAME = "NSIDC-0723"
VERSION = "4"
COLLECTION_ID = "nsidc-0723-v4"

ENDPOINT = "https://s3.kopah.uw.edu"
BUCKET = "gaia"
PREFIX = "public/grimp/nsidc-0723/v04"
S3_PREFIX = f"s3://{BUCKET}/{PREFIX}"
HTTPS_PREFIX = f"{ENDPOINT}/{BUCKET}/{PREFIX}"

LOCAL_DIR = Path("/tmp/grimp-cogs")

# e.g. GL_S1bks_mosaic_22Dec25_27Dec25_gamma0_50m_v04.0.tif
FILENAME_RE = re.compile(
    r"GL_S1bks_mosaic_(?P<start>\d{2}\w{3}\d{2})_(?P<end>\d{2}\w{3}\d{2})"
    r"_(?P<product>\w+?)_(?P<resolution>\d+m)_v(?P<version>[\d.]+)\.tif$"
)


def load_env(path=ROOT / ".env"):
    """Load KEY=VALUE lines from .env into os.environ (without overriding)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def parse_filename(name):
    """Return metadata parsed from a GRIMP mosaic filename."""
    m = FILENAME_RE.search(name)
    if not m:
        raise ValueError(f"Unrecognized filename: {name}")
    start = datetime.strptime(m["start"], "%d%b%y")
    end = datetime.strptime(m["end"], "%d%b%y").replace(hour=23, minute=59, second=59)
    return {
        "start_datetime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_datetime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "product": m["product"],
        "resolution": m["resolution"],
        "version": m["version"],
    }
