import type { Config } from 'tailwindcss';
import colors from './src/theme/colors.js';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors,
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
  future: { hoverOnlyWhenSupported: true },
} satisfies Config;
