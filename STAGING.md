# Staging COGs and building the indexes

How the data in the [README](README.md) gets onto Kopah. There are two steps, both run with [pixi](https://pixi.sh):

1. **Stage** ([scripts/stage_cogs.py](scripts/stage_cogs.py)): find the COGs in NASA CMR, download them from NSIDC's Earthdata Cloud, and upload them to the public Kopah prefix `s3://gaia/public/grimp/<dataset>/v<NN>/`.
2. **Index** ([scripts/build_index.py](scripts/build_index.py)): make a STAC Item per COG with the `rio stac` CLI (reading the public HTTPS URL), merge the per-product Items of each period into one Item with an asset per product, and write them to `<dataset>.parquet` (e.g. `nsidc-0723.parquet`) with rustac. The index embeds a STAC Collection and is uploaded next to the COGs.

Datasets are defined in `DATASETS` in [scripts/common.py](scripts/common.py), where you can add more. Scripts pick one with `--dataset` (default `nsidc-0723`).

## Credentials

You need your own:

- `EARTHDATA_TOKEN` in a `.env` file at the repo root (not checked in), for downloading from NSIDC
- an AWS profile named `kopah` with write access to the `gaia` bucket, e.g. in `~/.aws/config`:

  ```ini
  [profile kopah]
  endpoint_url = https://s3.kopah.uw.edu
  request_checksum_calculation = when_required
  response_checksum_validation = when_required
  ```

Run the local commands below with `AWS_PROFILE=kopah` set.

## Locally

```bash
pixi run stage --dry-run        # list the COGs that would be staged
pixi run stage --periods 3      # last 3 mosaic periods (3 products each); --periods 0 for all of 2025
pixi run index                  # rio-stac Items -> rustac -> nsidc-0723.parquet, uploaded next to the COGs

pixi run stage --dataset nsidc-0725 --periods 0   # all 9 years of velocity mosaics
pixi run index --dataset nsidc-0725

pixi run stage --dataset nsidc-0481 --start 2023-01-01 --periods 0 --workers 8   # 2023 glacier sites
pixi run index --dataset nsidc-0481 --workers 16
```

Use `pixi run index --no-upload` to build the index without uploading it. Local outputs (Items cache, ndjson, parquet) go to `output/<dataset>/`. Cached Items are reused, so rebuilding an index takes seconds; pass `--overwrite` to regenerate them.

By default each COG is downloaded, uploaded and deleted one at a time (`--workers 1`), so local disk use stays around one file (~3 GB for NSIDC-0723; a full year is ~355 GB). On home wifi, parallel transfers don't help for the large mosaics. For NSIDC-0481's small files (~0.6 MB each), per-file overhead dominates, so use `--workers 8`: 2023 (1,505 COGs, ~1 GB) staged in ~6 minutes from home wifi.

## On AWS us-west-2 with SkyPilot (much faster)

NSIDC's Earthdata Cloud data lives in us-west-2, so [recipes/stage_cogs.yaml](recipes/stage_cogs.yaml) runs both steps on a spot VM there. Credentials are passed as SkyPilot secrets by [scripts/sky_launch.sh](scripts/sky_launch.sh): `EARTHDATA_TOKEN` from `.env`, and the Kopah keys from the `kopah` AWS profile.

```bash
pixi run skypilot-login               # once
pixi run sky-stage --env PERIODS=3    # subset
pixi run sky-stage                    # all of 2025
pixi run sky-stage --env DATASET=nsidc-0725   # all NSIDC-0725 v5 years
pixi run sky-stage --env DATASET=nsidc-0481 --env WORKERS=32   # all NSIDC-0481 v4 (24k small files)
pixi run -e sky sky jobs logs <job-id>
```

Both steps skip work that's already done, so re-running (or a spot recovery) picks up where it left off.

## Dataset notes

- **NSIDC-0723 v4:** each 6- or 12-day period has three products. `gamma0` and `sigma0` are 50 m and `image` is 25 m, which is why `proj:shape`/`proj:transform` are stored per asset.
- **NSIDC-0725 v5:** 9 years x 7 COGs, ~13 GB total. `browse` is listed first because the RGB renders without a colormap.
- **NSIDC-0481 v4:** small maps of ~55 outlet-glacier sites, one per TSX/TDX image pair: 4,896 pairs x 5 COGs, ~24,500 files, ~15 GB total. Only 2023 is staged so far. Items are grouped per site and image pair (the filename's acquisition time distinguishes pairs of the same site and dates), and carry a `grimp:site` property.

Asset order in each index comes from `products` in the dataset definition; viewers that render "the first COG" show that product by default.
