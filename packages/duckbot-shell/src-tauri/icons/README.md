# Icons

This is the **official Duckbot mark**, not a drawing of it.

`mark-tiled.svg` is the artwork from the brand guide at https://duckbot.hk/en/brand/,
copied byte for byte from `mark-tiled.9ce2c1fb.svg` (the hash is the website build's, kept
here only so the source version is identifiable). The guide is explicit: *"The SVG is the
artwork — do not redraw it."*

The tiled mark is the correct choice for an application icon. The guide says so directly:
*"App icon: always the tiled mark. Yellow on white does not hold — do not put the yellow
standalone duck on a light content panel."*

## Regenerating

Everything else in this folder is generated from the SVG and is safe to delete and rebuild:

```bash
python -c "import cairosvg; cairosvg.svg2png(url='src-tauri/icons/mark-tiled.svg', \
  write_to='src-tauri/icons/icon-source.png', output_width=1024, output_height=1024)"
npx --yes "@tauri-apps/cli@^2" icon src-tauri/icons/icon-source.png -o src-tauri/icons
rm -rf src-tauri/icons/android src-tauri/icons/ios
```

The `android/` and `ios/` sets the generator produces are removed: this is a desktop-only
build, and thirty unused files are thirty files somebody eventually wonders about.

If the mark is ever revised, replace `mark-tiled.svg` from the brand page and re-run the
above. Do not edit the generated PNGs, and do not edit the SVG.

## The rules from the guide that bear on this folder

- Minimum size 16px. Our smallest generated icon is 32px, which holds comfortably.
- Do not put the duck back in a circle, restore the three dots, add a padlock or shield,
  recolour the tile, or outline, shadow or gradient the mark.
- Brand yellow is `#FFEC00`; ink is `#0C0B08`.
