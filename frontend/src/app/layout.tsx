import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";

import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl = process.env.BUSCASAM_BASE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "BUSCASAM — Trabajos académicos de la UNSAM",
    template: "%s — BUSCASAM",
  },
  description:
    "Buscador de trabajos académicos de la UNSAM: tesis, papers, monografías, trabajos prácticos y más, de la comunidad de la Universidad Nacional de San Martín.",
  applicationName: "BUSCASAM",
  openGraph: {
    type: "website",
    siteName: "BUSCASAM",
    locale: "es_AR",
    url: "/buscar",
    title: "BUSCASAM — Trabajos académicos de la UNSAM",
    description:
      "Buscador de trabajos académicos de la UNSAM: tesis, papers, monografías y más.",
  },
  twitter: { card: "summary_large_image" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <Providers>
          <SiteHeader />
          {children}
          <SiteFooter />
          <Toaster position="bottom-center" richColors />
        </Providers>
      </body>
    </html>
  );
}
