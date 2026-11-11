# Demo staging GRIMP draft data before it's published to NSIDC

Goal: Create an interface to easily visualize COGs on the web, and also allow programmatic access.

This is just a proof of concept using three datasets (see `DATASETS` in [scripts/common.py](scripts/common.py) to add more):

- the last year of S1 mosaics: https://nsidc.org/data/nsidc-0723/versions/4 (default, `--dataset nsidc-0723`)
- all annual velocity mosaics, Dec 2014 - Nov 2023: https://nsidc.org/data/nsidc-0725/versions/5 (`--dataset nsidc-0725`)
- all TerraSAR-X/TanDEM-X glacier-site velocity maps, 2008 - 2023: https://nsidc.org/data/nsidc-0481/versions/4 (`--dataset nsidc-0481`)

## Usage

### NSIDC-0481 v4 (selected glacier site velocity)

Unlike the Greenland-wide mosaics, these are small maps of ~55 outlet-glacier sites (e.g. `W69.10N` is Jakobshavn Isbræ), one per TSX/TDX image pair: 4,896 pairs x 5 COGs (`vv`, `vx`, `vy`, `ex`, `ey`, all 100 m EPSG:3413, ~0.6 MB each), ~24,500 files, ~15 GB total. Many sites share the same date range, so footprints mostly don't overlap and the indexes are easy to browse in STAC-map.

Only 2023 (Jan - Sep, the last year of data) is staged so far: 1,505 COGs, 301 image pairs at 38 sites, ~1 GB. It staged in ~6 minutes from home wifi with `--workers 8`, since per-file overhead dominates for small files:

```bash
pixi run stage --dataset nsidc-0481 --start 2023-01-01 --periods 0 --workers 8
pixi run index --dataset nsidc-0481 --workers 16
```

- COGs and indexes: https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/
- [items.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/items.parquet) (all products), one index per product (e.g. [vv.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/vv.parquet)), and [periods.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/periods.parquet) (one Item per site and image pair, `vv` asset first)
- Items carry a `grimp:site` property, so you can filter on a glacier, e.g. `filter="\"grimp:site\" = 'W69.10N'"` with rustac

### NSIDC-0725 v5 (annual velocity)

9 years x 7 COGs (`browse`, `vv`, `vx`, `vy`, `ex`, `ey`, `dT`, all 200 m EPSG:3413), ~13 GB total. Same layout as 0723 below:

- COGs and indexes: https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/
- [items.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/items.parquet) (all products), one index per product (e.g. [vv.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/vv.parquet), [browse.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/browse.parquet)), and [periods.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/periods.parquet) (one Item per year, `browse` asset first since the RGB renders without a colormap)

### NSIDC-0723 v4 (S1 backscatter)

- COGs and the index live at https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/
- STAC-Geoparquet index (all products): https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/items.parquet
- STAC-Geoparquet index, one Item per mosaic period with `gamma0`, `sigma0` and `image` assets: https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/periods.parquet

### STAC-MAP

Development Seed has an excellent STAC Map viewer that can read STAC-Geoparquet indexes. The standard STAC-map is geared towards non-overlapping polygons, so it doesn't work well with the GRIMP mosaics, so I created [fork of STAC-map](https://github.com/scottyhq/stac-map) to allow panning through rendered COGs in time with the arrow keys. You can then see STAC metadata per item, click download buttons, etc.

- A STAC-map fork demo with arrow keys to pan through time: https://scottyhq.github.io/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/gamma0.parquet

- STAC-map, one index per product:
  [gamma0](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/gamma0.parquet),
  [sigma0](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/sigma0.parquet),
  [image](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/image.parquet)

The three products share a footprint, so the per-product indexes are easier to browse in STAC-map. Alternatively, [periods.parquet](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/periods.parquet) has one footprint per period, with each product as an asset (projection shape/transform are per-asset since `image` is 25m). Set the time slider first, then click the footprint. Clicking an Item hides the slider; use "Clear selection" to get it back.

### Searching the index with rustac

See the [rustac docs](https://stac-utils.github.io/rustac-py/latest/) for more details.

Each Item covers one mosaic period (`start_datetime`/`end_datetime`). A date search returns every Item whose period overlaps the query range, so a range that touches the end of one period and the start of the next returns both.

CLI:

```bash
pixi shell
```

```bash
rustac search https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/gamma0.parquet \
  --datetime 2025-12-16T00:00:00Z/2025-12-20T00:00:00Z
```

Python (use the combined index and filter on product):

```python
import rustac

items = rustac.search_sync(
    "https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/items.parquet",
    datetime="2025-12-16T00:00:00Z/2025-12-20T00:00:00Z",
    filter="\"grimp:product\" = 'gamma0'",
)
for item in items:
    print(item["properties"]["start_datetime"], item["assets"]["data"]["href"])
```

Use `..` for an open-ended range, e.g. `2025-12-01T00:00:00Z/..`.

### Downloading

The rustac CLI has no download command, but `rustac search` can write ndjson to stdout, so you can pipe the asset hrefs through `jq` into `curl`. Everything is public over HTTPS, no credentials needed. For example, all `gamma0` mosaics overlapping December 2025 (5 files, ~11 GB):

```bash
rustac search https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/gamma0.parquet \
  --datetime 2025-12-01T00:00:00Z/2025-12-31T23:59:59Z -o ndjson \
  | jq -r '.assets[].href' \
  | xargs -n 1 -P 4 curl -sS --fail -C - -O --output-dir grimp-dec2025
```

Use `items.parquet` (all products) or add `--filter` to narrow the search, e.g. `--filter "\"grimp:product\" IN ('gamma0', 'sigma0')"`. `-P 4` runs four downloads at once, and `-C -` resumes partial files if you re-run. Drop the `xargs` line to just list the URLs first.

Alternatively, the bucket allows anonymous S3 access, so `aws s3 sync` works for a whole collection, or a subset with filename globs (the filenames start with the period's start date, so this differs slightly from the date-overlap search above, e.g. it skips `28Nov25_03Dec25`):

```bash
# whole collection
aws s3 sync --no-sign-request --endpoint-url https://s3.kopah.uw.edu \
  s3://gaia/public/grimp/nsidc-0725/v05/ nsidc-0725

# gamma0 periods starting in December 2025 (add --dryrun to preview)
aws s3 sync --no-sign-request --endpoint-url https://s3.kopah.uw.edu \
  s3://gaia/public/grimp/nsidc-0723/v04/ grimp-dec2025 \
  --exclude "*" --include "GL_S1bks_mosaic_??Dec25_*_gamma0_*.tif"
```

### Locally

```bash
pixi run stage --dry-run        # list the COGs that would be staged
pixi run stage --periods 3      # last 3 mosaic periods (3 products each); --periods 0 for all of 2025
pixi run index                  # rio-stac Items -> rustac -> items.parquet, uploaded next to the COGs

pixi run stage --dataset nsidc-0725 --periods 0   # all 9 years of velocity mosaics
pixi run index --dataset nsidc-0725

pixi run stage --dataset nsidc-0481 --periods 1   # one date range (a handful of sites)
pixi run index --dataset nsidc-0481
```

Local outputs (Items cache, ndjson, parquet) go to `output/<dataset>/`.

Each COG is downloaded, uploaded and deleted one at a time (`--workers 1`), so local disk use stays around one file (~3 GB); a full year is ~355 GB. On home wifi, parallel transfers don't help.

### On AWS us-west-2 with SkyPilot (much faster)

NSIDC's Earthdata Cloud data lives in us-west-2, so [recipes/stage_cogs.yaml](recipes/stage_cogs.yaml) runs both steps on a spot VM there. Credentials are passed as SkyPilot secrets: `EARTHDATA_TOKEN` from `.env`, and the Kopah keys from the `kopah` AWS profile.

```bash
pixi run skypilot-login               # once
pixi run sky-stage --env PERIODS=3    # subset
pixi run sky-stage                    # all of 2025
pixi run sky-stage --env DATASET=nsidc-0725   # all NSIDC-0725 v5 years
pixi run sky-stage --env DATASET=nsidc-0481 --env WORKERS=32   # all NSIDC-0481 v4 (24k small files)
pixi run -e sky sky jobs logs <job-id>
```

Both steps skip work that's already done, so re-running (or a spot recovery) picks up where it left off.



## Approach for staging data:

1. Use a public prefix for UW Kopah Object Storage (https://s3.kopah.uw.edu/gaia/public/grimp/) and Put a bunch of COGS (https://nsidc.org/data/nsidc-0723/versions/4) there. Since it's a proof of concept start we will just stage the last year of COGs. Download to /tmp/grimp-cogs using a parallelized script and then upload to the public prefix. Use the AWS CLI to do this, and make sure you have your AWS_PROFILE set to kopah.

2. Generate a STAC-Geoparquet Index for all
    2a. each COG needs a STAC, which we will generate using the rio-stac CLI
    2b. use rustac to generate a STAC-Geoparquet Index for all the STACs

3. point STAC-map at the STAC-Geoparquet Index URL

Notes:
- necessary KOPAH credentials are in the .env file, which is not checked into git. You will need to create your own AWS_PROFILE and EARTHDATA_TOKEN to run the code.
