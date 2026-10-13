# Toy ABM

A small disease-modeling agent-based model built around the ZIP code area 21550 in Maryland.

## Local setup

To run it locally:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
export CENSUS_API_KEY=see_below

.venv/bin/python run.py
```

Get the Census API key at: https://api.census.gov/data/key_signup.html

---

## Core data-loading functions

### `load_zone()`

No arguments. It always targets ZIP Code Tabulation Area 21550 in Maryland.

It loads two Census geography inputs from the local cache under `Toy_ABM/data/tiger/`:

- One polygon for ZCTA 21550 from the Census TIGERweb query (`ZCTA5='21550'`, GeoJSON, longitude/latitude), cached as `zcta_21550.geojson`
- Every Maryland block group for 2024 from the state shapefile `tl_2024_24_bg.zip`, downloaded from www2.census.gov

The function keeps the block groups whose polygons intersect the ZIP area, sorts them by `GEOID`, and projects both the ZIP polygon and the selected block groups to the local UTM zone so distances are stored in meters.

The returned object is a `ZoneGeometry`:

| Field | Meaning |
| --- | --- |
| `zcta` | The string `"21550"` |
| `metric_crs` | The UTM code, such as `"EPSG:32617"` |
| `geoids` | A list of 12-digit block-group IDs |
| `zcta_wgs84` / `zcta_meters` | A one-row GeoDataFrame in degrees and meters |
| `block_groups_wgs84` / `block_groups_meters` | One row per intersecting block group, including a `geoid` column and polygon |

The current cache uses 16 of those block groups. The state file contains every Maryland block group, but only the ones touching 21550 remain in the zone.

### `load_census(zone)`

This function uses the input `zone` and validates that each `GEOID` belongs to Garrett County (`24023`).

It loads two ACS 5-year 2023 tables from https://api.census.gov/data/2023/acs/acs5, cached under `Toy_ABM/data/census/`:

- `acs5_2023_bg_24023.json`: every block group in Garrett County. This file is a list of lists. Row 0 is the header, with 52 columns: `name`, total population `B01003_001E`, 46 sex-by-age counts from `B01001`, then `state`, `county`, `tract`, and `block group`. The cache includes 24 data rows covering the whole county.
- `acs5_2023_county_24023.json`: a single county row of household counts (`B11001`, `B11003`, `B11016`) for Garrett County, including totals for family, nonfamily, families with children, and household size.

The function drops any county block groups not in `zone.geoids`. Each kept row becomes a `BlockGroupCensus` with:

- `geoid`
- `population` (one integer)
- `sex_age`, a tuple of 46 `SexAgeCount` values with fields `(sex, min_age, max_age, count)`

The return value is a `CensusCounts`:

- `block_groups`: a dictionary keyed by `GEOID`, with one `BlockGroupCensus` per zone block group; the current cache has 16 entries.
- `households`: one `CountyHouseholds` object shared by every block group. It stores integer totals plus two dictionaries, `family_size_counts` and `nonfamily_size_counts`, keyed by household size 1–7.

### `load_places(zone)`

This input is the zone outline based on `zone.zcta_wgs84.total_bounds` and the meter polygon. It does not use the census.

It reads one Overpass download from https://overpass-api.de/api/interpreter, cached as `Toy_ABM/data/osm/overpass_21550.json`.

The query requests nodes and ways tagged as:

- `amenity` in `school`, `pharmacy`, `clinic`, or `hospital`
- anything tagged `shop` or `office`
- located inside the ZIP bounding box

The cached payload is a dictionary with an `elements` list; the file contains 180 elements. Each element is an OSM object with tags and either lat/lon or a center.

The function keeps only points inside the ZIP polygon and maps tags to a place function:

- `school`
- `pharmacy`
- `clinic`
- `grocery` for supermarket or convenience stores
- `workplace` for any other shop or office

If the extract had no school or no grocery, the code would insert an Oakland placeholder. This extract includes both, so no placeholder is added.

The return value is a list of `Place` objects, sorted by function, then name, then latitude, then longitude, and numbered `P1`, `P2`, ...

Current totals in the dataset are:

- 137 workplaces
- 20 schools
- 10 groceries
- 2 pharmacies
- 1 clinic

Each `Place` includes:

- `place_id`
- `name`
- `latitude`
- `longitude`
- `function`
- `cbg` (the block group containing the point, or `None`)
- `placeholder`

---

## Town generation

### `build_town(zone, census, places)`

This function uses the three objects above and a fixed seed of `42`. It performs no network calls.

For each block group, it draws households until the total number of people matches that block group's ACS population. Household size and family-versus-nonfamily odds come from the county-level `CountyHouseholds` data. Sex and age are drawn from that block group's 46 population buckets.

The home coordinate is a random point inside the block-group polygon, then converted back to latitude and longitude. A resident's role is assigned by age:

- `student` for ages 5–17
- `worker` with probability 0.65 for ages 18–64
- `worker` with probability 0.10 for ages 65+
- otherwise `home`

The model also assigns:

- the nearest school for households with students
- the nearest grocery store
- a random workplace for each worker

The returned object is a `Town` with:

- `people`: a tuple of `Person` objects; the current town has 17,767 people. Fields include `person_id`, `home_id`, `home_cbg`, `sex`, `age`, `role`, `school_id`, `work_id`, and `grocery_id`.
- `homes`: a tuple of `Home` objects; the current town has 7,944 homes. Fields include `home_id`, `cbg`, `latitude`, `longitude`, and `members`.
- `places`: the same 170 `Place` objects, stored as a tuple.

After that, `run_clock` wraps each `Person` in a Mesa agent. These four calls stop at the `Town`.

> In other words, the workflow is: zone → census → places → town → simulated clock.