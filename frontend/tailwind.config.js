/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#0E1A2B", 2: "#1A2A40", 3: "#2B3B52" },
        paper: "#F6F4EF",
        surface: "#FFFFFF",
        line: { DEFAULT: "#E4E0D6", strong: "#D3CDBF" },
        muted: "#5B6575",
        accent: { DEFAULT: "#12A594", ink: "#0B7A6D", soft: "#E3F4F1" },
        confirmed: { DEFAULT: "#0F7B4F", soft: "#E5F2EB" },
        genuine: { DEFAULT: "#2563A8", soft: "#E8EFF8" },
        suspicious: { DEFAULT: "#B26B00", soft: "#FBF0DE" },
        fake: { DEFAULT: "#C2302B", soft: "#FAE7E5" },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      borderRadius: { xl: "0.75rem", "2xl": "1rem" },
      boxShadow: {
        card: "0 1px 2px rgba(14,26,43,0.04)",
        pop: "0 8px 24px rgba(14,26,43,0.12)",
      },
    },
  },
  plugins: [],
};
