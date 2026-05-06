import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "F5 Distributed Cloud Dashboard",
  description: "F5 Distributed Cloud read-only visibility",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-carbon-900 text-carbon-100 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
