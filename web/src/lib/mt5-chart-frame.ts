/** Crop MT5 ChartScreenShot to the right-hand setup frame and fatten candles.
 *
 * VPS ChartScreenShot packs hundreds of M1 bars as ~1px strokes. We keep the
 * right-hand setup slice, upscale, then horizontally dilate bright candle
 * pixels so bodies read as real candles (not hairlines).
 */
import sharp from "sharp";

const KEEP_RIGHT_FRACTION = 0.24;
const OUT_SIZE = 720;
/** How many pixels to expand each candle column left/right. */
const CANDLE_FAT_RADIUS = 2;

function isCandlePixel(r: number, g: number, b: number): boolean {
  // MT5 bull/bear bodies on black — bright green or red-ish strokes.
  if (g > 90 && g >= r + 25 && g >= b + 25) return true;
  if (r > 90 && r >= g + 25 && r >= b + 25) return true;
  return false;
}

function fattenCandleColumns(
  data: Buffer,
  width: number,
  height: number,
  radius: number,
): Buffer {
  const out = Buffer.from(data);
  const bpp = 4; // RGBA
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * bpp;
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const a = data[i + 3];
      if (!isCandlePixel(r, g, b)) continue;
      for (let dx = -radius; dx <= radius; dx++) {
        const nx = x + dx;
        if (nx < 0 || nx >= width) continue;
        const j = (y * width + nx) * bpp;
        // Don't paint over axis text (near-white).
        const or_ = out[j];
        const og = out[j + 1];
        const ob = out[j + 2];
        const bright = or_ > 180 && og > 180 && ob > 180;
        if (bright) continue;
        out[j] = r;
        out[j + 1] = g;
        out[j + 2] = b;
        out[j + 3] = a;
      }
    }
  }
  return out;
}

export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  const meta = await sharp(png).metadata();
  const width = meta.width ?? 0;
  const height = meta.height ?? 0;
  if (width < 200 || height < 200) return png;

  const keep = Math.max(Math.floor(width * KEEP_RIGHT_FRACTION), 180);
  const left = Math.max(width - keep, 0);

  const framed = await sharp(png)
    .extract({ left, top: 0, width: keep, height })
    .resize(OUT_SIZE, OUT_SIZE, {
      fit: "fill",
      kernel: "nearest",
    })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const fat = fattenCandleColumns(
    framed.data,
    framed.info.width,
    framed.info.height,
    CANDLE_FAT_RADIUS,
  );

  return sharp(fat, {
    raw: {
      width: framed.info.width,
      height: framed.info.height,
      channels: 4,
    },
  })
    .png()
    .toBuffer();
}
