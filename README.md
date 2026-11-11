# GrIMP draft data as Cloud-Optimized GeoTIFFs + STAC-Geoparquet

A proof of concept for browsing and accessing MEaSUREs Greenland Ice Mapping Project (GrIMP) data on the web before it's published at NSIDC. The COGs are mirrored on UW Kopah object storage, and each dataset has a single [STAC-Geoparquet](https://github.com/stac-utils/stac-geoparquet) index you can open in a web map or search from Python or the command line.

Everything is public over HTTPS. No credentials needed.

## Datasets

Each index has one STAC Item per mosaic period (or image pair), with one asset per product. All COGs are in EPSG:3413.

| Dataset | Coverage | Products (assets) | Index | Browse |
|---|---|---|---|---|
| [NSIDC-0723 v4](https://nsidc.org/data/nsidc-0723/versions/4) Sentinel-1 backscatter mosaics | 2025, 6/12-day periods | `gamma0`, `sigma0` (dB, 50 m), `image` (8-bit, 25 m) | [nsidc-0723.parquet](https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/nsidc-0723.parquet) | [STAC-map (GrIMP fork)](https://scottyhq.github.io/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/nsidc-0723.parquet) · [upstream](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/nsidc-0723.parquet) |
| [NSIDC-0725 v5](https://nsidc.org/data/nsidc-0725/versions/5) annual velocity mosaics | Dec 2014 - Nov 2023, yearly | `browse` (RGB), `vv`, `vx`, `vy`, `ex`, `ey`, `dT` (200 m) | [nsidc-0725.parquet](https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/nsidc-0725.parquet) | [STAC-map (GrIMP fork)](https://scottyhq.github.io/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/nsidc-0725.parquet) · [upstream](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0725/v05/nsidc-0725.parquet) |
| [NSIDC-0481 v4](https://nsidc.org/data/nsidc-0481/versions/4) TerraSAR-X/TanDEM-X glacier site velocity | Jan - Sep 2023 so far (301 image pairs at 38 sites) | `vv`, `vx`, `vy`, `ex`, `ey` (100 m) | [nsidc-0481.parquet](https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/nsidc-0481.parquet) | [STAC-map (GrIMP fork)](https://scottyhq.github.io/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/nsidc-0481.parquet) · [upstream](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/nsidc-0481.parquet) |

The COGs sit next to each index, e.g. https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/.

Item properties include `start_datetime`/`end_datetime` for the period and `grimp:version`. NSIDC-0481 Items also have `grimp:site`, the glacier site name (e.g. `W69.10N` is Jakobshavn Isbræ). Asset `title`, `gsd`, `proj:shape` and `proj:transform` are per asset, since resolution can differ between products.

## Browsing in STAC-map

The **Browse** links in the table open a [fork of STAC-map](https://github.com/scottyhq/stac-map) with a few customizations for GrIMP data:

- **Better time slider:** step through mosaic periods with the arrow keys, and keep the slider while an Item is selected
- **Dynamic colormaps:** colormap and log scaling for single-band COGs such as velocity and backscatter
- **Hover values:** read the pixel value under the cursor

We intend to contribute these features to Development Seed's [STAC-map](https://github.com/developmentseed/stac-map) over time. The indexes are standard STAC-Geoparquet and also work in the [currently deployed upstream STAC-map](https://developmentseed.org/stac-map/) (the "upstream" links), just without these extras. Further development should happen in the upstream repository.

STAC-map renders the COGs in the browser and shows the first asset of each Item: `gamma0` for NSIDC-0723, the RGB `browse` image for NSIDC-0725, and `vv` for NSIDC-0481. The Greenland-wide mosaics all share one footprint, so pick a period with the time slider, then click the footprint to see its metadata and download links. The NSIDC-0481 sites mostly don't overlap, so they are easier to browse.

## Searching with rustac

[rustac](https://stac-utils.github.io/rustac-py/latest/) can search a STAC-Geoparquet file over HTTPS without downloading it. Install it with `pip install rustac` (or `pixi shell` in this repo).

Each Item covers one period (`start_datetime`/`end_datetime`). A date search returns every Item whose period overlaps the query range, so a range that touches the end of one period and the start of the next returns both. Use `..` for an open-ended range, e.g. `2025-12-01T00:00:00Z/..`.

Python:

```python
import rustac

items = rustac.search_sync(
    "https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/nsidc-0723.parquet",
    datetime="2025-12-16T00:00:00Z/2025-12-20T00:00:00Z",
)
for item in items:
    print(item["properties"]["start_datetime"], item["assets"]["gamma0"]["href"])
```

CLI, filtering NSIDC-0481 to one glacier:

```bash
rustac search https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0481/v04/nsidc-0481.parquet \
  --filter "\"grimp:site\" = 'W69.10N'"
```

## Downloading

`rustac search` can write ndjson to stdout, so you can pipe the asset hrefs through `jq` into `curl`. For example, all `gamma0` mosaics overlapping December 2025 (5 files, ~11 GB):

```bash
rustac search https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/nsidc-0723.parquet \
  --datetime 2025-12-01T00:00:00Z/2025-12-31T23:59:59Z -o ndjson \
  | jq -r '.assets.gamma0.href' \
  | xargs -n 1 -P 4 curl -sS --fail -C - -O --output-dir grimp-dec2025
```

Use `jq -r '.assets[].href'` for every product, or e.g. `jq -r '.assets.gamma0.href, .assets.sigma0.href'` for a subset. `-P 4` runs four downloads at once, and `-C -` resumes partial files if you re-run. Drop the `xargs` line to just list the URLs first.

The bucket also allows anonymous S3 access, so `aws s3 sync` works for a whole collection, or a subset with filename globs. The filenames start with the period's start date, so this differs slightly from the date-overlap search above (e.g. it skips `28Nov25_03Dec25`):

```bash
# whole collection
aws s3 sync --no-sign-request --endpoint-url https://s3.kopah.uw.edu \
  s3://gaia/public/grimp/nsidc-0725/v05/ nsidc-0725

# gamma0 periods starting in December 2025 (add --dryrun to preview)
aws s3 sync --no-sign-request --endpoint-url https://s3.kopah.uw.edu \
  s3://gaia/public/grimp/nsidc-0723/v04/ grimp-dec2025 \
  --exclude "*" --include "GL_S1bks_mosaic_??Dec25_*_gamma0_*.tif"
```

## More

- [STAGING.md](STAGING.md): how the COGs are copied to Kopah and the indexes are built
- [NOTES.md](NOTES.md): why browsers can't read the NASA-hosted COGs directly, so the data is mirrored
