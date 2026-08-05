import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";

const geist = Geist({
  variable: "--font-geist",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const baseUrl = new URL(`${protocol}://${host}`);
  const description = "Relatório gerencial de remessas e retornos por projeto.";

  return {
    metadataBase: baseUrl,
    title: "Painel de Pintura MTECH",
    description,
    icons: {
      icon: "/favicon.svg",
      shortcut: "/favicon.svg",
    },
    openGraph: {
      title: "Painel de Pintura MTECH",
      description,
      type: "website",
      images: [{ url: new URL("/og.png", baseUrl), width: 1672, height: 941, alt: "Painel de Pintura MTECH" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "Painel de Pintura MTECH",
      description,
      images: [new URL("/og.png", baseUrl)],
    },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className={geist.variable}>{children}</body>
    </html>
  );
}
