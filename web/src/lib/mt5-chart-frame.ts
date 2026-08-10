/** Crop MT5 ChartScreenShot to the right-hand setup frame and upscale.
 *
 * ChartOpen/OBJ_CHART on a VPS still packs hundreds of M1 bars into the PNG.
 * Structure (sweep→entry) sits on the right; keep that slice and nearest-
 * neighbor upscale so candles read thick in the site/Telegram preview.
 */
import sharp from "sharp";

/** Fraction of image width to keep (from the right edge, includes price axis).
 * Lower = fewer bars after upscale = fatter candles. ~0.28 keeps the setup
 * (sweep→entry) while making M1 bodies readable. */
const KEEP_RIGHT_FRACTION = 0.28;
const OUT_SIZE = 720;

export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  const meta = await sharp(png).metadata();
  const width = meta.width ?? 0;
  const height = meta.height ?? 0;
  if (width < 200 || height < 200) return png;

  const keep = Math.max(Math.floor(width * KEEP_RIGHT_FRACTION), 160);
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
