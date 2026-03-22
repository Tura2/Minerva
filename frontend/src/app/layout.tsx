import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import { ThemeProvider } from "@/lib/ThemeProvider";
import { Analytics } from "@vercel/analytics/next";

export const metadata: Metadata = {
  title: "Minerva — Trading Research Copilot",
  description: "Automated swing-trading research with structured entry/exit rules",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          <Nav />
          <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
          <Analytics />
        </ThemeProvider>
      </body>
    </html>
  );
}
