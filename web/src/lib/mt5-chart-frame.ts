/** Soft-upscale narrow MT5 ChartScreenShot to display size.
 *
 * No crop, no candle dilation — those ruined the terminal look. Fat candles
 * come from a narrower EA embed at scale 0; we only lanczos-upscale here.
 */
import sharp from "sharp";

const OUT_W = 1280;
const OUT_H = 720;

export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  const meta = await sharp(png).metadata();
  const width = meta.width ?? 0;
  const height = meta.height ?? 0;
  if (width < 100 || height < 100) return png;
  if (width >= OUT_W && height >= OUT_H) return png;

  return sharp(png)
    .resize(OUT_W, OUT_H, {
      fit: "fill",
      kernel: "lanczos3",
    })
    .png()
    .toBuffer();
}
