export function rms(samples) {
  if (!samples.length) return 0;
  return Math.sqrt(samples.reduce((sum, v) => sum + v * v, 0) / samples.length);
}
export function mouthScale(samples) {
  return Math.min(1, rms(samples) * 5);
}
