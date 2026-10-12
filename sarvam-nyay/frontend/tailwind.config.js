/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  // Class-based dark mode — the <html> element gets a `dark` class toggled
  // by useTheme(). System preference is the initial value; the user can
  // override and we persist their pick in localStorage.
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#EEF0F7",
          100: "#D4D8EC",
          200: "#A9B1D9",
          300: "#7E8AC6",
          400: "#5363B3",
          500: "#1B2B5E",  // VeriDictum primary navy
          600: "#16235C",  // primary
          700: "#111A47",
          800: "#0C1231",
          900: "#07091B",
        },
        gold: {
          50: "#FDF8EC",
          100: "#FAEECE",
          200: "#F5DC9D",
          300: "#EFCA6C",
          400: "#E9B83B",
          500: "#C9A84C",  // VeriDictum gold
          600: "#B8922A",
          700: "#8A6D1F",
          800: "#5C4914",
          900: "#2E240A",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      keyframes: {
        // Skeleton shimmer — used by components/atoms/Skeleton.tsx
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        // Vera AI glow — a soft, slow gold pulse behind the assistant avatar
        veraPulse: {
          "0%, 100%": { opacity: "0.55", transform: "scale(1)" },
          "50%":      { opacity: "1",    transform: "scale(1.08)" },
        },
        // Subtle in-page hint that something is "live" / streaming
        breath: {
          "0%, 100%": { opacity: "0.6" },
          "50%":      { opacity: "1"   },
        },
      },
      animation: {
        shimmer:   "shimmer 1.6s ease-in-out infinite",
        veraPulse: "veraPulse 2.6s ease-in-out infinite",
        breath:    "breath 2s ease-in-out infinite",
      },
      boxShadow: {
        // Premium "AI" elevation used on Vera bubbles and the glass tile
        glow: "0 0 0 1px rgba(201, 168, 76, 0.25), 0 10px 30px -10px rgba(201, 168, 76, 0.45)",
      },
    },
  },
  plugins: [],
};
