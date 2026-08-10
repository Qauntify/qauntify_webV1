/** Crop MT5 ChartScreenShot to the right-hand setup frame and upscale.
 *
 * ChartOpen/OBJ_CHART on a VPS still packs hundreds of M1 bars into the PNG.
 * Structure (sweep→entry) sits on the right; keep that slice, stretch width
 * harder than height (nearest-neighbor), then take the right square so candle
 * bodies read thick in the site/Telegram preview.
 */
import sharp from "sharp";

/** Fraction of source width to keep from the right (includes price axis). */
const KEEP_RIGHT_FRACTION = 0.32;
/** Horizontal stretch vs output size — higher = fatter candles. */
const WIDTH_STRETCH = 2.1;
const OUT_SIZE = 720;

export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  const meta = await sharp(png).metadata();
  const width = meta.width ?? 0;
  const height = meta.height ?? 0;
  if (width < 200 || height < 200) return png;

  const keep = Math.max(Math.floor(width * KEEP_RIGHT_FRACTION), 160);
  const left = Math.max(width - keep, 0);
  const stretchedW = Math.max(Math.round(OUT_SIZE * WIDTH_STRETCH), OUT_SIZE + 80);

  // 1) crop setup slice  2) inflate width (fat bars)  3) take right OUT_SIZE square
  const stretched = await sharp(png)
    .extract({ left, top: 0, width: keep, height })
    .resize(stretchedW, OUT_SIZE, {
      fit: "fill",
      kernel: "nearest",
    })
    .png()
    .toBuffer();

  return sharp(stretched)
    .extract({
      left: stretchedW - OUT_SIZE,
      top: 0,
      width: OUT_SIZE,
      height: OUT_SIZE,
    })
    .png()
    .toBuffer();
}
