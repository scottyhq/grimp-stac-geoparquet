"""Shared configuration for the GRIMP staging demo.

Each staged NSIDC dataset is described by a `Dataset` in `DATASETS`; scripts pick
one with `--dataset` (default: nsidc-0723).
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENDPOINT = "https://s3.kopah.uw.edu"
BUCKET = "gaia"


@dataclass(frozen=True)
class Dataset:
    short_name: str  # CMR short name, e.g. NSIDC-0723
    version: str  # CMR version, e.g. "4"
    # Must define start, end, product and version groups, and a `tag` group
    # spanning the product (+ resolution) part that differs between the files
    # of one mosaic period (or granule). resolution and site are optional.
    # Also used to pick the COGs out of each CMR granule's data links.
    filename_re: re.Pattern
    # Asset order in <key>.parquet; viewers that render "the first COG" show
    # products[0] by default. Products not listed are appended alphabetically.
    products: list
    default_start: str
    default_end: str
    title: str
    description: str
    keywords: list = field(default_factory=list)

    @property
    def key(self):  # nsidc-0723
        return self.short_name.lower()

    @property
    def collection_id(self):  # nsidc-0723-v4
        return f"{self.key}-v{self.version}"

    @property
    def nsidc_url(self):
        return f"https://nsidc.org/data/{self.key}/versions/{self.version}"

    @property
    def prefix(self):  # public/grimp/nsidc-0723/v04
        return f"public/grimp/{self.key}/v{int(self.version):02d}"

    @property
    def s3_prefix(self):
        return f"s3://{BUCKET}/{self.prefix}"

    @property
    def https_prefix(self):
        return f"{ENDPOINT}/{BUCKET}/{self.prefix}"

    @property
    def local_dir(self):
        return Path("/tmp/grimp-cogs") / self.key

    @property
    def out_dir(self):
        return ROOT / "output" / self.key

    def parse_filename(self, name):
        """Return metadata parsed from a GRIMP mosaic filename."""
        basename = name.rsplit("/", 1)[-1]
        m = self.filename_re.search(basename)
        if not m:
            raise ValueError(f"Unrecognized {self.short_name} filename: {name}")
        start = datetime.strptime(m["start"], "%d%b%y")
        end = datetime.strptime(m["end"], "%d%b%y").replace(hour=23, minute=59, second=59)
        return {
            "start_datetime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_datetime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": m["product"],
            "resolution": m.groupdict().get("resolution"),
            "site": m.groupdict().get("site"),
            "version": m["version"],
            # Item id for the merged per-period Item, i.e. the name minus the tag
            # (for per-site datasets, one Item per site and period)
            "period_id": (basename[: m.start("tag")] + basename[m.end("tag") :]).removesuffix(".tif"),
        }


DATASETS = {
    d.key: d
    for d in [
        Dataset(
            short_name="NSIDC-0723",
            version="4",
            # e.g. GL_S1bks_mosaic_22Dec25_27Dec25_gamma0_50m_v04.0.tif
            filename_re=re.compile(
                r"GL_S1bks_mosaic_(?P<start>\d{2}\w{3}\d{2})_(?P<end>\d{2}\w{3}\d{2})"
                r"(?P<tag>_(?P<product>\w+?)_(?P<resolution>\d+m))_v(?P<version>[\d.]+)\.tif$"
            ),
            products=["gamma0", "sigma0", "image"],
            default_start="2025-01-01",
            default_end="2025-12-31",
            title="GrIMP Sentinel-1 Greenland Image Mosaics (NSIDC-0723 v4)",
            description=(
                "Draft 2025 Sentinel-1 SAR mosaics of Greenland from the MEaSUREs Greenland "
                "Ice Mapping Project (GrIMP), staged as Cloud-Optimized GeoTIFFs ahead of "
                "NSIDC publication. Each 6- or 12-day period has three products: gamma0 and "
                "sigma0 calibrated backscatter (dB, 50 m) and an 8-bit image (25 m), all in "
                "EPSG:3413."
            ),
            keywords=["GrIMP", "MEaSUREs", "Greenland", "Sentinel-1", "SAR", "backscatter"],
        ),
        Dataset(
            short_name="NSIDC-0725",
            version="5",
            # e.g. GL_vel_mosaic_Annual_01Dec22_30Nov23_vv_v05.0.tif
            filename_re=re.compile(
                r"GL_vel_mosaic_Annual_(?P<start>\d{2}\w{3}\d{2})_(?P<end>\d{2}\w{3}\d{2})"
                r"(?P<tag>_(?P<product>[A-Za-z]+))_v(?P<version>[\d.]+)\.tif$"
            ),
            # browse (RGB uint8) first: it renders without a colormap/rescale
            products=["browse", "vv", "vx", "vy", "ex", "ey", "dT"],
            default_start="2014-01-01",
            default_end="2025-12-31",
            title="GrIMP Greenland Annual Ice Sheet Velocity Mosaics (NSIDC-0725 v5)",
            description=(
                "Annual (December-November) ice velocity mosaics of the Greenland Ice Sheet "
                "from the MEaSUREs Greenland Ice Mapping Project (GrIMP), derived from "
                "TerraSAR-X/TanDEM-X, Sentinel-1 and Landsat 8/9. Each year has velocity "
                "magnitude (vv), components (vx, vy), errors (ex, ey), dT and an RGB browse "
                "image, all 200 m Cloud-Optimized GeoTIFFs in EPSG:3413."
            ),
            keywords=["GrIMP", "MEaSUREs", "Greenland", "ice velocity", "SAR", "Landsat"],
        ),
        Dataset(
            short_name="NSIDC-0481",
            version="4",
            # e.g. TSX_W76.25N_09Sep23_20Sep23_20-44-38_vv_v04.0.tif
            # site is a glacier-site name (W76.25N, E66.50N, S46.91W, ...); the
            # HH-MM-SS acquisition time distinguishes pairs of the same site and dates
            filename_re=re.compile(
                r"TSX_(?P<site>[NSEW]\d+\.\d+[NSEW])_(?P<start>\d{2}\w{3}\d{2})_(?P<end>\d{2}\w{3}\d{2})"
                r"_\d{2}-\d{2}-\d{2}(?P<tag>_(?P<product>[A-Za-z]+))_v(?P<version>[\d.]+)\.tif$"
            ),
            products=["vv", "vx", "vy", "ex", "ey"],
            default_start="2008-01-01",
            default_end="2025-12-31",
            title="GrIMP Greenland Selected Glacier Site Velocity Maps from InSAR (NSIDC-0481 v4)",
            description=(
                "Ice velocity maps of major Greenland outlet glaciers from the MEaSUREs "
                "Greenland Ice Mapping Project (GrIMP), derived from TerraSAR-X/TanDEM-X "
                "image pairs (2008-2023, ~55 glacier sites). Each image pair has velocity "
                "magnitude (vv), components (vx, vy) and errors (ex, ey), all 100 m "
                "Cloud-Optimized GeoTIFFs in EPSG:3413."
            ),
            keywords=["GrIMP", "MEaSUREs", "Greenland", "ice velocity", "InSAR", "TerraSAR-X", "TanDEM-X"],
        ),
    ]
}
DEFAULT_DATASET = "nsidc-0723"


def add_dataset_arg(parser):
    parser.add_argument(
        "--dataset", choices=sorted(DATASETS), default=DEFAULT_DATASET,
        help="Which NSIDC dataset to stage/index",
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
