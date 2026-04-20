Useful scripts I build for different software.


## Python

### `scripts/edge_points.py` – High-pass edge point sampler

Loads an image, computes a Difference-of-Gaussians (high-pass) importance map, and
probabilistically samples a set of points concentrated around high-frequency edges.
Points are **not** simply the top-k strongest edges – a temperature/alpha parameter
controls how random the sampling is, and a minimum-distance constraint keeps them
spread out.

**Dependencies** (install once via `pip install -r requirements.txt`):
```
opencv-python, numpy, Pillow
```

#### Usage

```bash
# Basic – 40 points, visualisation saved to points.png
python scripts/edge_points.py --input photo.jpg --out points.png

# Full control
python scripts/edge_points.py \
  --input photo.jpg \
  --out points.png \
  --num-points 40 \
  --sigma 3 \
  --alpha 2.0 \
  --threshold 0.05 \
  --min-dist 20 \
  --seed 123 \
  --points-json points.json \
  --points-csv  points.csv

# Dry-run (prints coordinates, writes nothing)
python scripts/edge_points.py --input photo.jpg --dry-run --num-points 10
```

#### CLI reference

| Flag | Default | Description |
|------|---------|-------------|
| `--input / -i` | *(required)* | Input image path (PNG, JPG, …) |
| `--out / -o` | `points.png` | Output visualisation image |
| `--num-points / -n` | `40` | Number of points to sample |
| `--sigma / -s` | `3.0` | Gaussian sigma for high-pass filter |
| `--alpha / -a` | `2.0` | Sampling exponent – `>1` focuses on strong edges, `<1` more random |
| `--threshold / -t` | `0.05` | Minimum normalised importance to consider (0–1) |
| `--min-dist / -d` | `20` | Minimum pixel distance between sampled points |
| `--marker-radius` | `14` | Circle marker radius in pixels |
| `--font-size` | `12` | Label font size in pt |
| `--seed` | *(none)* | Random seed for reproducibility |
| `--points-json` | *(none)* | Save coordinates as JSON |
| `--points-csv` | *(none)* | Save coordinates as CSV |
| `--dry-run` | *(off)* | Print points without writing any files |

---

## Houdini
```
Houdini > radial_menu_display_options.py
```

A pie menu to toggle the different display options (e.g. Display points, Display point normals, etc.). It also works 
with custom markers. 

![Screenshot showing the display options pie menu](https://raw.githubusercontent.com/sms-cx/dat/main/.github/images/screenshot_display_piemenu.png)  

### Installation:

1. Open Houdini
2. Edit > Radial Menus...
3. Add menu
4. Set a name and label
5. Paste the code
