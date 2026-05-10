// Custom multi-layer shadow set inspired by the Minimal UI Kit.
// MUI's default elevations are too sharp / too dark for this aesthetic;
// these are softer, with a small offset and large blur at low alpha so
// cards float without a heavy outline.

const ALPHA = 0.16;
const BG = `145, 158, 171`; // rgb of palette.grey[500]; matches the kit's reference.

const z = (offsetY: number, blur: number, second?: { y: number; blur: number; alpha: number }) => {
  const layers = [
    `0 ${offsetY}px ${blur}px 0 rgba(${BG}, ${ALPHA})`,
  ];
  if (second) {
    layers.unshift(`0 ${second.y}px ${second.blur}px 0 rgba(${BG}, ${second.alpha})`);
  }
  return layers.join(', ');
};

export const customShadows = {
  z1: z(2, 8, { y: 1, blur: 2, alpha: 0.08 }),
  z4: z(4, 12, { y: 1, blur: 3, alpha: 0.08 }),
  z8: z(8, 16, { y: 2, blur: 4, alpha: 0.08 }),
  z12: z(12, 24, { y: 4, blur: 8, alpha: 0.08 }),
  z16: z(16, 32, { y: 4, blur: 12, alpha: 0.08 }),
  z20: z(20, 40, { y: 6, blur: 16, alpha: 0.08 }),
  z24: z(24, 48, { y: 8, blur: 20, alpha: 0.08 }),
  card: '0px 0px 2px 0px rgba(145, 158, 171, 0.08), 0px 12px 24px -4px rgba(145, 158, 171, 0.12)',
  dropdown:
    '0 0 2px 0 rgba(145, 158, 171, 0.24), -20px 20px 40px -4px rgba(145, 158, 171, 0.24)',
  primary: '0 8px 16px 0 rgba(0, 167, 111, 0.24)',
};

// MUI requires a 25-element array for shadows[0..24].
const noShadow = 'none';
export const shadowsArray: string[] = [
  noShadow,
  customShadows.z1,
  customShadows.z1,
  customShadows.z4,
  customShadows.z4,
  customShadows.z8,
  customShadows.z8,
  customShadows.z8,
  customShadows.z8,
  customShadows.z12,
  customShadows.z12,
  customShadows.z12,
  customShadows.z16,
  customShadows.z16,
  customShadows.z16,
  customShadows.z20,
  customShadows.z20,
  customShadows.z20,
  customShadows.z20,
  customShadows.z20,
  customShadows.z24,
  customShadows.z24,
  customShadows.z24,
  customShadows.z24,
  customShadows.z24,
];
