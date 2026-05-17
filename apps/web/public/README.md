# public/

Static assets served from the site root.

## Icon notes

`favicon.ico` and `apple-touch-icon.png` are currently raw copies of `alphora.png`. Most browsers accept a PNG payload at the `.ico` URL, but to produce a real multi-resolution ICO with 16x16, 32x32, and 48x48 frames and a properly sized 180x180 apple-touch-icon, regenerate via:

```
sips -z 16 16 alphora.png --out favicon-16.png
sips -z 32 32 alphora.png --out favicon-32.png
sips -z 180 180 alphora.png --out apple-touch-icon.png
```

Then combine the PNGs into a multi-frame `.ico` using a tool such as ImageMagick (`magick favicon-16.png favicon-32.png favicon.ico`).
