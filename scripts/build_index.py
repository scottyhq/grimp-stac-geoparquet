"""Step 2: build a STAC-Geoparquet index of the COGs staged on Kopah.

2a. Generate a STAC Item per COG with the rio-stac CLI (reading the public HTTPS URL)
2b. Combine Items into stac-geoparquet with the rustac CLI, then upload it

Usage:
    python scripts/build_index.py
    python scripts/build_index.py --no-upload
"""

import argparse
import asyncio
import json
import subprocess

import rustac
from concurrent.futures import ThreadPoolExecutor

from common import (
    COLLECTION_ID,
    HTTPS_PREFIX,
    ROOT,
    S3_PREFIX,
    load_env,
    parse_filename,
)
from stage_cogs import existing_keys

OUT_DIR = ROOT / "output"
ITEMS_DIR = OUT_DIR / "items"
INDEX_NAME = "items.parquet"
PERIODS_INDEX_NAME = "periods.parquet"
# Asset order matters: viewers that render "the first COG" show gamma0 by default
PRODUCTS = ["gamma0", "sigma0", "image"]
ASSET_LEVEL_PROJ = ["proj:shape", "proj:transform"]  # differ by resolution


def make_item(name, overwrite):
    item_id = name.removesuffix(".tif")
    path = ITEMS_DIR / f"{item_id}.json"
    if path.exists() and not overwrite:
        return path
    meta = parse_filename(name)
    subprocess.run(
        [
            "rio", "stac", f"{HTTPS_PREFIX}/{name}",
            "--id", item_id,
            "--collection", COLLECTION_ID,
            "--datetime", meta["start_datetime"],
            "--property", f"start_datetime={meta['start_datetime']}",
            "--property", f"end_datetime={meta['end_datetime']}",
            "--property", f"grimp:product={meta['product']}",
            "--property", f"grimp:resolution={meta['resolution']}",
            "--property", f"grimp:version={meta['version']}",
            "--asset-name", "data",
            "--asset-mediatype", "COG",
            "--without-eo",
            "--densify-geom", "21",
            "--geom-precision", "6",
            "--output", str(path),
        ],
        check=True,
    )
    return path


NSIDC_URL = "https://nsidc.org/data/nsidc-0723/versions/4"
COLLECTION_TITLE = "GrIMP Sentinel-1 Greenland Image Mosaics (NSIDC-0723 v4)"
COLLECTION_DESCRIPTION = (
    "Draft 2025 Sentinel-1 SAR mosaics of Greenland from the MEaSUREs Greenland Ice "
    "Mapping Project (GrIMP), staged as Cloud-Optimized GeoTIFFs ahead of NSIDC "
    "publication. Each 6- or 12-day period has three products: gamma0 and sigma0 "
    "calibrated backscatter (dB, 50 m) and an 8-bit image (25 m), all in EPSG:3413. "
    f"Dataset documentation: [NSIDC-0723 v4]({NSIDC_URL})."
)


def make_collection(items):
    """STAC Collection (extents from the Items) embedded in each geoparquet file."""
    collection = rustac.collection_from_id_and_items(COLLECTION_ID, items)
    collection.update(
        title=COLLECTION_TITLE,
        description=COLLECTION_DESCRIPTION,
        license="other",
        keywords=["GrIMP", "MEaSUREs", "Greenland", "Sentinel-1", "SAR", "backscatter"],
        providers=[
            {"name": "NSIDC DAAC", "roles": ["producer", "licensor"], "url": NSIDC_URL},
        ],
    )
    collection["links"] = [
        {"rel": "about", "href": NSIDC_URL, "type": "text/html", "title": "NSIDC-0723 v4 dataset page"},
        {"rel": "license", "href": NSIDC_URL, "type": "text/html", "title": "NSIDC data use and citation"},
    ]
    return collection


def merge_by_period(items):
    """Combine the per-product Items of each mosaic period into one multi-asset Item.

    All products in a period share a footprint, so one Item per period with
    gamma0 / sigma0 / image assets lets a viewer toggle products in place.
    """
    groups = {}
    for item in items:
        p = item["properties"]
        groups.setdefault((p["start_datetime"], p["end_datetime"]), {})[p["grimp:product"]] = item

    merged = []
    for (start, end), by_product in sorted(groups.items()):
        first = by_product[next(k for k in PRODUCTS if k in by_product)]
        if len({json.dumps(i["geometry"]) for i in by_product.values()}) > 1:
            raise ValueError(f"Products for {start} have different footprints")

        props = {
            k: v
            for k, v in first["properties"].items()
            if k not in ("grimp:product", "grimp:resolution", *ASSET_LEVEL_PROJ)
        }
        assets = {}
        for product in [k for k in PRODUCTS if k in by_product] + sorted(set(by_product) - set(PRODUCTS)):
            src = by_product[product]
            asset = dict(src["assets"]["data"])
            asset["title"] = f"{product} ({src['properties']['grimp:resolution']})"
            asset["roles"] = ["data"]
            asset["gsd"] = float(src["properties"]["grimp:resolution"].removesuffix("m"))
            for k in ASSET_LEVEL_PROJ:
                asset[k] = src["properties"][k]
            assets[product] = asset

        # GL_S1bks_mosaic_02Jan25_13Jan25_gamma0_50m_v04.0 -> GL_S1bks_mosaic_02Jan25_13Jan25_v04.0
        item_id = first["id"].replace(
            f"_{first['properties']['grimp:product']}_{first['properties']['grimp:resolution']}", ""
        )
        merged.append({**first, "id": item_id, "properties": props, "assets": assets})
    return merged


async def write_geoparquet(items, path):
    async with rustac.geoparquet_writer(items, str(path)) as writer:
        writer.add_collection(make_collection(items))


def write_index(name, items, upload=True):
    """Write Items to OUT_DIR/name as stac-geoparquet and optionally upload it."""
    ndjson = OUT_DIR / name.replace(".parquet", ".ndjson")
    ndjson.write_text("".join(json.dumps(i) + "\n" for i in items))
    parquet = OUT_DIR / name
    asyncio.run(write_geoparquet(items, parquet))
    print(f"Wrote {parquet} ({len(items)} Items)")

    if upload:
        subprocess.run(
            [
                "aws", "s3", "cp", "--only-show-errors",
                "--content-type", "application/vnd.apache.parquet",
                str(parquet), f"{S3_PREFIX}/{name}",
            ],
            check=True,
        )
        url = f"{HTTPS_PREFIX}/{name}"
        print(f"  STAC-map: https://developmentseed.org/stac-map/?href={url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing Items")
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    load_env()
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)

    names = sorted(k for k in existing_keys() if k.endswith(".tif"))
    print(f"Generating STAC Items for {len(names)} COGs")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        paths = list(pool.map(lambda n: make_item(n, args.overwrite), names))

    items = []
    for path in paths:
        item = json.loads(path.read_text())
        # rio-stac CLI can't set asset roles
        item["assets"]["data"]["roles"] = ["data"]
        items.append(item)
    # Write rows in time order (filenames sort by day of month). In STAC-map the
    # last row is drawn on top, so clicking a stack of footprints picks the newest.
    items.sort(key=lambda i: (i["properties"]["start_datetime"], i["id"]))

    # One index with everything, plus one per product: products share footprints,
    # so in STAC-map a click on the combined index can't pick a product
    indexes = {INDEX_NAME: items}
    for product in sorted({i["properties"]["grimp:product"] for i in items}):
        indexes[f"{product}.parquet"] = [
            i for i in items if i["properties"]["grimp:product"] == product
        ]

    # One Item per period with an asset per product
    indexes[PERIODS_INDEX_NAME] = merge_by_period(items)

    for name, subset in indexes.items():
        write_index(name, subset, upload=not args.no_upload)

if __name__ == "__main__":
    main()
