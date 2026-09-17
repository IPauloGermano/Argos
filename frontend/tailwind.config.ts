/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fffbeb",
          100: "#fef3c7",
          200: "#fde68a",
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b", // Hermes Amber Gold
          600: "#d97706",
          700: "#b45309",
          800: "#92400e",
          900: "#78350f",
        },
        surface: {
          base: "#0e1015",       // Canvas carvão mineral
          card: "#151820",       // Painel grafite quente
          elevated: "#1c202b",   // Superfície de contraste/hover
          interactive: "#232836",// Elementos selecionados
          border: "#282d3c",     // Borda sutil precisa
          borderLight: "#353c4f",// Borda iluminada
        },
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", "'Times New Roman'", "serif"],
      },
    },
  },
  plugins: [],
};
