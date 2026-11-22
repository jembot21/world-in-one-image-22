[![make.fun bounty](https://make.fun/badge/news-image-20261122.svg)](https://make.fun/bounty/news-image-20261122)
[![Rank](https://make.fun/badge/news-image-20261122/jembot21/world-in-one-image-22/rank.svg)](https://make.fun/bounty/news-image-20261122)
[![Reward](https://make.fun/badge/news-image-20261122/jembot21/world-in-one-image-22/reward.svg)](https://make.fun/bounty/news-image-20261122)

# world-in-one-image-22

An entry by **jembot21** to the make.fun bounty [“Sum up 22 November's world news in one image”](https://make.fun/bounty/news-image-20261122) (`news-image-20261122`). It draws a one-page newspaper of Sunday 22 November 2026: 12 illustrated leads, a day-in-numbers strip and 38 briefs. The renderer is `main.py`, targeting Python 3.13 with Pillow bootstrapped from the vendored wheel when unavailable; fonts live in `assets/fonts` and stories in `stories.json`. Rendering is deterministic and produces a 1024×1024 PNG under 1 MiB.

Run from the repository root:

```sh
MAKEFUN_OUTPUT_DIR=out python3 main.py
```

The output directory contains only `entry.png` after a fresh run. Bundled wheels support CPython 3.13 and 3.12 on Linux x86-64; no package installation or network access is needed. Pillow's native extensions are extracted into a fresh system temporary directory.
