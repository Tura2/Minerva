import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import ResearchToast from "@/components/ResearchToast";
import { ThemeProvider } from "@/lib/ThemeProvider";
import { ResearchProvider } from "@/lib/ResearchContext";
import { Analytics } from "@vercel/analytics/next";

export const metadata: Metadata = {
  title: "Minerva — Trading Research Copilot",
  description: "Automated swing-trading research with structured entry/exit rules",
  icons: {
    icon: [
      { url: "/icon.png", sizes: "512x512", type: "image/png" },
    ],
    apple: "/icon.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          <ResearchProvider>
            <div className="flex min-h-screen">
              <Sidebar />
              <div className="flex-1 min-w-0 flex flex-col">
                <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8">
                  {children}
                </main>
              </div>
            </div>
            <ResearchToast />
          </ResearchProvider>
        </ThemeProvider>
        <Analytics />
      </body>
    </html>
  );
}
