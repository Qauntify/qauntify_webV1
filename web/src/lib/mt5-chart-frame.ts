/** Soft-frame MT5 ChartScreenShot — crop + lanczos only.
 *
 * Never dilate candle pixels (that turns charts into neon slabs). We only
 * keep the right-hand setup slice and upscale smoothly so labels stay clean.
 */
import sharp from "sharp";

/** Keep the right half — mild zoom without destroying MT5 pixels. */
const KEEP_RIGHT_FRACTION = 0.5;
const OUT_SIZE = 720;

export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  const meta = await sharp(png).metadata();
  const width = meta.width ?? 0;
  const height = meta.height ?? 0;
  if (width < 200 || height < 200) return png;

  // Narrow EA shots already have fat native candles — soft upscale only.
  if (width <= 480) {
    return sharp(png)
      .resize(OUT_SIZE, OUT_SIZE, {
        fit: "fill",
        kernel: "lanczos3",
      })
      .png()
      .toBuffer();
  }

  const keep = Math.max(Math.floor(width * KEEP_RIGHT_FRACTION), 280);
  const left = Math.max(width - keep, 0);

  return sharp(png)
    .extract({ left, top: 0, width: keep, height })
    .resize(OUT_SIZE, OUT_SIZE, {
      fit: "fill",
      kernel: "lanczos3",
    })
    .png()
    .toBuffer();
}
