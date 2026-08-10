/** Crop MT5 ChartScreenShot to the right-hand setup frame and upscale.
 *
 * ChartOpen/OBJ_CHART on a VPS still packs hundreds of M1 bars into the PNG.
 * Keep the right-hand setup slice and nearest-neighbor upscale to OUT_SIZE so
 * candle bodies read thicker. (Do not stretch-then-recrop the right edge —
 * that leaves only the price axis.)
 */
import sharp from "sharp";

/** Lower = fewer bars in frame = fatter candles after upscale. */
const KEEP_RIGHT_FRACTION = 0.22;
const OUT_SIZE = 720;

export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  const meta = await sharp(png).metadata();
  const width = meta.width ?? 0;
  const height = meta.height ?? 0;
  if (width < 200 || height < 200) return png;

  const keep = Math.max(Math.floor(width * KEEP_RIGHT_FRACTION), 180);
  const left = Math.max(width - keep, 0);

  return sharp(png)
    .extract({ left, top: 0, width: keep, height })
    .resize(OUT_SIZE, OUT_SIZE, {
      fit: "fill",
      kernel: "nearest",
    })
    .png()
    .toBuffer();
}
