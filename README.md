# Demo staging GRIMP draft data before it's published to NSIDC

Goal: Create an interface to easily visualize COGs on the web, and also allow programmatic access.

This is just a proof of concept using the last year of S1 mosaics: https://nsidc.org/data/nsidc-0723/versions/4

## Usage

- COGs and the index live at https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/
- STAC-Geoparquet index (all products): https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/items.parquet

### STAC-MAP

Development Seed has an excellent STAC Map viewer that can read STAC-Geoparquet indexes. The standard STAC-map is geared towards non-overlapping polygons, so it doesn't work well with the GRIMP mosaics, so I created [fork of STAC-map](https://github.com/scottyhq/stac-map) to allow panning through rendered COGs in time with the arrow keys. You can then see STAC metadata per item, click download buttons, etc.

- A STAC-map fork demo with arrow keys to pan through time: https://scottyhq.github.io/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/gamma0.parquet

- STAC-map, one index per product:
  [gamma0](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/gamma0.parquet),
  [sigma0](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/sigma0.parquet),
  [image](https://developmentseed.org/stac-map/?href=https://s3.kopah.uw.edu/gaia/public/grimp/nsidc-0723/v04/image.parquet)

The three products share a footprint, so the per-product indexes are easier to browse in STAC-map. Set the time slider first, then click the footprint. Clicking an Item hides the slider; use "Clear selection" to get it back.

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

### Locally

```bash
pixi run stage --dry-run        # list the COGs that would be staged
pixi run stage --periods 3      # last 3 mosaic periods (3 products each); --periods 0 for all of 2025
pixi run index                  # rio-stac Items -> rustac -> items.parquet, uploaded next to the COGs
```

Each COG is downloaded, uploaded and deleted one at a time (`--workers 1`), so local disk use stays around one file (~3 GB); a full year is ~355 GB. On home wifi, parallel transfers don't help.

### On AWS us-west-2 with SkyPilot (much faster)

NSIDC's Earthdata Cloud data lives in us-west-2, so [recipes/stage_cogs.yaml](recipes/stage_cogs.yaml) runs both steps on a spot VM there. Credentials are passed as SkyPilot secrets: `EARTHDATA_TOKEN` from `.env`, and the Kopah keys from the `kopah` AWS profile.

```bash
pixi run skypilot-login               # once
pixi run sky-stage --env PERIODS=3    # subset
pixi run sky-stage                    # all of 2025
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
