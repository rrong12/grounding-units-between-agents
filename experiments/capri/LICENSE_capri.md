# License

This dataset has **two licensing layers**:

1. **Conversations, annotations, metadata, and scoring keys** (everything under
   `conversations/`, the `random_index.json` metadata, `ground_truth_units.json`,
   and `country_list.json`) — (c) the CulturalPragmatics authors, licensed
   **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/).

2. **Images** — third-party photographs, AI-generated images, and author-made
   graphics. Per-image licenses are in `licenses/ATTRIBUTION.md` (TASL manifest)
   and the per-concept CSVs (`licenses/{price,speed,temperature,time}.csv`,
   columns `name, URL, License`).
   - **Photographs** — sourced from Flickr under CC BY 2.0 / CC BY-SA 2.0 /
     CC BY 4.0 / CC0, except **two CC BY-ND 2.0 photos**
     (`images/time/camera/1245.jpg`, `images/time/camera/1400.jpg`): these are
     redistributed **verbatim** as received; do **not** redistribute modified
     versions of these two files.
   - **AI-generated images** (`images/distance/`, `images/size/`,
     `images/temperature/aigen/`, `images/time/aigen/`) — produced with
     Google's image-generation models at collection time.
   - **Author-made graphics** (`images/quantifiers/`) — the quantifier images
     were manually created by the authors and are released under **CC BY 4.0**
     (https://creativecommons.org/licenses/by/4.0/).
