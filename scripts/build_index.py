"""Step 2: build a STAC-Geoparquet index of the COGs staged on Kopah.

2a. Generate a STAC Item per COG with the rio-stac CLI (reading the public HTTPS URL)
2b. Combine Items into stac-geoparquet with the rustac CLI, then upload it

Usage:
    python scripts/build_index.py
    python scripts/build_index.py --no-upload
    python scripts/build_index.py --dataset nsidc-0725
"""

import argparse
import asyncio
import json
import subprocess

import rustac
from concurrent.futures import ThreadPoolExecutor

from common import DATASETS, add_dataset_arg, load_env
from stage_cogs import existing_keys

INDEX_NAME = "items.parquet"
PERIODS_INDEX_NAME = "periods.parquet"
ASSET_LEVEL_PROJ = ["proj:shape", "proj:transform"]  # may differ by resolution


def make_item(ds, name, overwrite):
    item_id = name.removesuffix(".tif")
    path = ds.out_dir / "items" / f"{item_id}.json"
    if path.exists() and not overwrite:
        return path
    meta = ds.parse_filename(name)
    props = {
        "start_datetime": meta["start_datetime"],
        "end_datetime": meta["end_datetime"],
        "grimp:product": meta["product"],
        "grimp:resolution": meta["resolution"],
        "grimp:version": meta["version"],
    }
    subprocess.run(
        [
            "rio", "stac", f"{ds.https_prefix}/{name}",
            "--id", item_id,
            "--collection", ds.collection_id,
            "--datetime", meta["start_datetime"],
            *[a for k, v in props.items() if v for a in ("--property", f"{k}={v}")],
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


def make_collection(ds, items):
    """STAC Collection (extents from the Items) embedded in each geoparquet file."""
    collection = rustac.collection_from_id_and_items(ds.collection_id, items)
    collection.update(
        title=ds.title,
        description=f"{ds.description} Dataset documentation: [{ds.short_name} v{ds.version}]({ds.nsidc_url}).",
        license="other",
        keywords=ds.keywords,
        providers=[
            {"name": "NSIDC DAAC", "roles": ["producer", "licensor"], "url": ds.nsidc_url},
        ],
    )
    collection["links"] = [
        {"rel": "about", "href": ds.nsidc_url, "type": "text/html", "title": f"{ds.short_name} v{ds.version} dataset page"},
        {"rel": "license", "href": ds.nsidc_url, "type": "text/html", "title": "NSIDC data use and citation"},
    ]
    return collection


def merge_by_period(ds, items):
    """Combine the per-product Items of each mosaic period into one multi-asset Item.

    All products in a period share a footprint, so one Item per period with
    an asset per product lets a viewer toggle products in place.
    """
    groups = {}
    for item in items:
        p = item["properties"]
        groups.setdefault((p["start_datetime"], p["end_datetime"]), {})[p["grimp:product"]] = item

    merged = []
    for (start, end), by_product in sorted(groups.items()):
        order = [k for k in ds.products if k in by_product] + sorted(set(by_product) - set(ds.products))
        first = by_product[order[0]]
        if len({json.dumps(i["geometry"]) for i in by_product.values()}) > 1:
            raise ValueError(f"Products for {start} have different footprints")

        props = {
            k: v
            for k, v in first["properties"].items()
            if k not in ("grimp:product", "grimp:resolution", *ASSET_LEVEL_PROJ)
        }
        assets = {}
        for product in order:
            src = by_product[product]
            asset = dict(src["assets"]["data"])
            gsd = abs(src["properties"]["proj:transform"][0])
            asset["title"] = f"{product} ({gsd:g}m)"
            asset["roles"] = ["data"]
            asset["gsd"] = float(gsd)
            for k in ASSET_LEVEL_PROJ:
                asset[k] = src["properties"][k]
            assets[product] = asset

        # GL_S1bks_mosaic_02Jan25_13Jan25_gamma0_50m_v04.0 -> GL_S1bks_mosaic_02Jan25_13Jan25_v04.0
        item_id = ds.parse_filename(f"{first['id']}.tif")["period_id"]
        merged.append({**first, "id": item_id, "properties": props, "assets": assets})
    return merged


async def write_geoparquet(ds, items, path):
    async with rustac.geoparquet_writer(items, str(path)) as writer:
        writer.add_collection(make_collection(ds, items))


def write_index(ds, name, items, upload=True):
    """Write Items to ds.out_dir/name as stac-geoparquet and optionally upload it."""
    ndjson = ds.out_dir / name.replace(".parquet", ".ndjson")
    ndjson.write_text("".join(json.dumps(i) + "\n" for i in items))
    parquet = ds.out_dir / name
    asyncio.run(write_geoparquet(ds, items, parquet))
    print(f"Wrote {parquet} ({len(items)} Items)")

    if upload:
        subprocess.run(
            [
                "aws", "s3", "cp", "--only-show-errors",
                "--content-type", "application/vnd.apache.parquet",
                str(parquet), f"{ds.s3_prefix}/{name}",
            ],
            check=True,
        )
        url = f"{ds.https_prefix}/{name}"
        print(f"  STAC-map: https://developmentseed.org/stac-map/?href={url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_dataset_arg(parser)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing Items")
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()
    ds = DATASETS[args.dataset]

    load_env()
    (ds.out_dir / "items").mkdir(parents=True, exist_ok=True)

    names = sorted(k for k in existing_keys(ds) if k.endswith(".tif"))
    print(f"Generating STAC Items for {len(names)} {ds.short_name} COGs")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        paths = list(pool.map(lambda n: make_item(ds, n, args.overwrite), names))

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
    indexes[PERIODS_INDEX_NAME] = merge_by_period(ds, items)

    for name, subset in indexes.items():
        write_index(ds, name, subset, upload=not args.no_upload)


if __name__ == "__main__":
    main()
