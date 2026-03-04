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
          bg: 'rgb(var(--astral-bg) / <alpha-value>)',
          surface: 'rgb(var(--astral-surface) / <alpha-value>)',
          primary: 'rgb(var(--astral-primary) / <alpha-value>)',
          secondary: 'rgb(var(--astral-secondary) / <alpha-value>)',
          text: 'rgb(var(--astral-text) / <alpha-value>)',
          muted: 'rgb(var(--astral-muted) / <alpha-value>)',
          accent: 'rgb(var(--astral-accent) / <alpha-value>)',
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
