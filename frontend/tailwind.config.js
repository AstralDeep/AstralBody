/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        astral: {
          bg: '#0F1221',
          surface: '#1A1E2E',
          primary: '#6366F1',
          secondary: '#8B5CF6',
          text: '#F3F4F6',
          muted: '#9CA3AF',
          accent: '#06B6D4',
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
