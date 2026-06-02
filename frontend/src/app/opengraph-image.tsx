import { ImageResponse } from "next/og";

export const alt = "BUSCASAM — Trabajos académicos de la UNSAM";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// The brand mark from Wordmark.tsx: blue rounded square with a white
// magnifying glass. Inlined as a data URI so Satori renders it reliably.
const MARK = `data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 26 26">
    <rect width="26" height="26" rx="7.5" fill="#1d4ed8"/>
    <circle cx="11" cy="11" r="4.4" fill="none" stroke="#fff" stroke-width="2.1"/>
    <path d="M14.4 14.4 18.5 18.5" stroke="#fff" stroke-width="2.1" stroke-linecap="round"/>
  </svg>`,
)}`;

export default function OgImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "90px",
        background: "#ffffff",
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <img src={MARK} width={96} height={96} alt="" />
        <div
          style={{
            display: "flex",
            fontSize: 76,
            fontWeight: 700,
            letterSpacing: -2,
          }}
        >
          <span style={{ color: "#171717" }}>BUSCA</span>
          <span style={{ color: "#1d4ed8" }}>SAM</span>
        </div>
      </div>
      <div
        style={{
          marginTop: 40,
          fontSize: 52,
          fontWeight: 600,
          letterSpacing: -1,
          color: "#171717",
        }}
      >
        Trabajos académicos de la UNSAM
      </div>
      <div style={{ marginTop: 20, fontSize: 30, color: "#737373" }}>
        Tesis, papers, monografías y más · buscasam.org
      </div>
    </div>,
    size,
  );
}
