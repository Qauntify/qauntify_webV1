/** Pass-through — keep the MT5 ChartScreenShot as the EA produced it. */
export async function tightFrameSetupPng(png: Buffer): Promise<Buffer> {
  return png;
}
