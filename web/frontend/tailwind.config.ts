import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        kakao: {
          yellow: "#FEE500",
          brown: "#3C1E1E",
          cream: "#FFF9E8",
          peach: "#FFE8D6",
          mint: "#E8F8F0",
        },
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 8px 32px rgba(60, 30, 30, 0.08)",
      },
    },
  },
  plugins: [],
};
export default config;
