# Notes

## Can a browser read the NASA-hosted COGs directly? (tested 2026-11-10)

**Short answer: no.** stac-map renders COGs in the browser with deck.gl-raster, so the
browser has to fetch byte ranges itself. NSIDC's download endpoint does not send CORS
headers, so the browser discards the responses no matter how you authenticate. That is why
the asset hrefs in `output/<dataset>/<dataset>.parquet` point at the public Kopah mirror
(`s3.kopah.uw.edu/gaia/public/grimp/...`) and not at NASA.

### What was tested

Test file: the 50 m gamma0 mosaic for 02Jan25–13Jan25 (NSIDC-0723 v4). Its NASA URL, from CMR:

```
https://data.nsidc.earthdatacloud.nasa.gov/nsidc-cumulus-prod-protected/MEASURES/NSIDC-0723/4/2025/01/02/GL_S1bks_mosaic_02Jan25_13Jan25_gamma0_50m_v04.0.tif
```

The requests below were sent with curl, adding an `Origin` header to imitate what a browser sends.

| Request | Response | CORS headers |
|---|---|---|
| Preflight `OPTIONS` (for `Authorization` and `Range` headers) | 405 | none |
| Range GET, no credentials | 302 to Earthdata Login | none |
| Range GET with `Authorization: Bearer <EDL token>` | 303 to a signed CloudFront URL | none |
| Range GET with only the EDL session cookie (`asf-urs`) | 303 to the signed CloudFront URL | none |
| Range GET on the signed CloudFront URL | 206, correct bytes | none |
| Preflight on the signed CloudFront URL | 403 | none |
| Range GET on the Kopah mirror | 206 | `Access-Control-Allow-Origin: *` |

Each credential route fails for its own reason:

- **`EARTHDATA_TOKEN` env var:** a web page can't read environment variables. A page that
  had the token anyway would have to send an `Authorization` header, which triggers a
  preflight, and the endpoint answers the preflight with 405.
- **`~/.netrc`:** only command-line tools (curl, GDAL, earthaccess) read it. Browsers don't.
- **Earthdata Login cookie:** the browser attaches it and the server accepts it, but the
  303 redirect it returns has no `Access-Control-Allow-Origin`. The browser stops at that
  first hop.

Authentication itself works: an authenticated client gets the bytes. Only the missing CORS
headers stop the browser.

### Is the missing CORS deliberate?

The likely answer is that CORS is **off by default and NSIDC hasn't turned it on**. Nobody
had to actively block browsers.

- NASA DAACs serve protected data through the
  [Thin Egress App (TEA)](https://github.com/asfadmin/thin-egress-app), the Cumulus egress
  service. Per the [TEA deployment docs](https://tea-docs.asf.alaska.edu/deploying/),
  CORS is opt-in for each deployment. It is turned on with `UseCorsCookieDomain` (which
  needs `CookieDomain` set) plus an optional allowlist, `AllowedCorsOrigins`. The
  allowlist supports subdomain wildcards such as `https://*.asf.alaska.edu`. The docs
  don't mention a bare `*`, so it may not be supported.
- Requests with different `Origin` values, including NASA's own web apps, got no CORS
  headers and a 405 on preflight. The origins tried were `search.earthdata.nasa.gov`,
  `worldview.earthdata.nasa.gov`, `nsidc.org`, the endpoint's own domain, and
  `example.com`. So NSIDC has no origin allowlist configured, not even for NASA sites.
- No public statement explains why. Plausible reasons, none confirmed:
  - TEA's CORS support is designed around cookies and a list of trusted origins. It
    doesn't open up to arbitrary third-party sites.
  - Earthdata Login exists to track and report users. Arbitrary sites making credentialed
    cross-origin requests would complicate that and raise security concerns.
  - The DAAC pays for egress.

Whether this was a conscious policy choice or just the default left in place can't be
determined from outside. Asking NSIDC User Services would settle it.

### Options for browser rendering

1. **Public CORS-enabled mirror** (current approach): copy the COGs to Kopah, which sends
   `Access-Control-Allow-Origin: *`.
2. **Proxy:** a small service that injects the EDL token and adds CORS headers to the
   responses. It costs egress through the proxy, and it exposes your credentials to anyone
   who can reach the proxy unless you restrict access.
3. **Server-side tiler** (e.g. TiTiler with a `.netrc`): the browser gets PNG/WebP tiles
   instead of reading COGs, so rendering is no longer client-side.
