import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PatchProof | Bug Reproduction & Patch Verification Platform",
  description: "Don't trust generated code. Prove it works.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full dark">
      <body className="min-h-full flex flex-col bg-slate-950 text-slate-100 antialiased font-sans">
        {children}
      </body>
    </html>
  );
}
