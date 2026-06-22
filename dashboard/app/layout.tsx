import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Nomaya — Compliance Agent Evaluation",
  description: "Provider-agnostic compliance evaluation suite for AI agents in financial services.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
