/** Pass-through for MT5 ChartScreenShot — keep the terminal look intact.
 *
 * Older EA builds may still send tight_frame=true; we no longer crop/dilate
 * because that destroyed candle quality. Upload the PNG as MT5 produced it.
 */
export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  return png;
}
