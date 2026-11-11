"""Step 1: stage GRIMP COGs (NSIDC-0723 v4, NSIDC-0725 v5) on Kopah public object storage.

Finds COGs via CMR, then for each file (in parallel): download from NSIDC with
an Earthdata bearer token -> upload to Kopah with the AWS CLI -> delete the local
copy. Streaming per file keeps local disk use bounded (a full year is ~355 GB).

Usage:
    python scripts/stage_cogs.py --periods 3          # last 3 mosaic periods
    python scripts/stage_cogs.py --periods 0          # everything in the date range
    python scripts/stage_cogs.py --dry-run
    python scripts/stage_cogs.py --dataset nsidc-0725 --periods 0
"""

import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import earthaccess

from common import DATASETS, add_dataset_arg, load_env

COG_CONTENT_TYPE = "image/tiff; application=geotiff; profile=cloud-optimized"


def find_cogs(ds, start, end, periods, products):
    parse_filename = ds.parse_filename
    granules = earthaccess.search_data(
        short_name=ds.short_name, version=ds.version, temporal=(start, end)
    )
    urls = [
        url
        for g in granules
        for url in g.data_links()
        if url.endswith(".tif") and "_mosaic_" in url
    ]
    if products:
        urls = [u for u in urls if parse_filename(u)["product"] in products]
    # Keep only mosaics that start within the requested range
    urls = [u for u in urls if start <= parse_filename(u)["start_datetime"][:10] <= end]
    if periods:
        starts = sorted({parse_filename(u)["start_datetime"] for u in urls})[-periods:]
        urls = [u for u in urls if parse_filename(u)["start_datetime"] in starts]
    return sorted(urls)


def existing_keys(ds):
    result = subprocess.run(
        ["aws", "s3", "ls", f"{ds.s3_prefix}/"], capture_output=True, text=True
    )
    # Non-zero exit just means the prefix doesn't exist yet
    return {line.split()[-1] for line in result.stdout.splitlines() if line.strip()}


def stage(ds, url, keep):
    name = url.rsplit("/", 1)[-1]
    local = ds.local_dir / name
    subprocess.run(
        [
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--retry", "3",
            "--header", f"Authorization: Bearer {os.environ['EARTHDATA_TOKEN']}",
            "--output", str(local),
            url,
        ],
        check=True,
    )
    subprocess.run(
        [
            "aws", "s3", "cp", "--only-show-errors",
            "--content-type", COG_CONTENT_TYPE,
            str(local), f"{ds.s3_prefix}/{name}",
        ],
        check=True,
    )
    if not keep:
        local.unlink()
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_dataset_arg(parser)
    parser.add_argument("--start", help="Default depends on --dataset")
    parser.add_argument("--end", help="Default depends on --dataset")
    parser.add_argument(
        "--periods", type=int, default=3,
        help="Only stage the N most recent mosaic periods (0 = all)",
    )
    parser.add_argument(
        "--products", nargs="*", default=None,
        help="Subset of products, e.g. gamma0 sigma0 image (0723) or vv browse (0725)",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Parallel transfers (1 is best on home wifi; more helps in AWS)",
    )
    parser.add_argument("--keep", action="store_true", help="Keep local copies")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ds = DATASETS[args.dataset]
    start = args.start or ds.default_start
    end = args.end or ds.default_end

    load_env()
    urls = find_cogs(ds, start, end, args.periods, args.products)
    done = existing_keys(ds)
    todo = [u for u in urls if u.rsplit("/", 1)[-1] not in done]
    print(f"{len(urls)} COGs selected, {len(urls) - len(todo)} already staged, {len(todo)} to go")

    if args.dry_run:
        for u in todo:
            print(u)
        return

    ds.local_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(stage, ds, u, args.keep): u for u in todo}
        for i, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            try:
                print(f"[{i}/{len(todo)}] staged {future.result()}")
            except subprocess.CalledProcessError as e:
                failures.append(url)
                print(f"[{i}/{len(todo)}] FAILED {url}: {e}")

    if failures:
        raise SystemExit(f"{len(failures)} failures; re-run to retry")


if __name__ == "__main__":
    main()
