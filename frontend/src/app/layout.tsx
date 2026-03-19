import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Minerva - Trading Research Copilot",
  description: "Automated swing-trading research with structured entry/exit rules",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
