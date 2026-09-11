import type { Metadata } from "next";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/geist/400.css";
import "@fontsource/geist/500.css";
import "@fontsource/geist/600.css";
import "@fontsource/geist/700.css";
import "./globals.css";
import "./premium.css";
import "./operations.css";
import "./auth-quick.css";
import "./scm.css";
import "./scm-v1.css";
import "./platform.css";
import "./scm-product.css";
import "./product-system.css";
import { V2Providers } from "@/components/operations/V2Providers";

export const metadata: Metadata = {
  title: "GenuineGigs Manufacturing Intelligence",
  description: "Procurement, supply-chain planning and factory operations in one manufacturing intelligence system."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><V2Providers>{children}</V2Providers></body>
    </html>
  );
}
