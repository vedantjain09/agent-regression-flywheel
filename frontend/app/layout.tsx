import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

// Note: next/font/google (Geist) was tried first but this build
// environment has no network route to fonts.googleapis.com (the same
// class of sandbox network restriction documented in
// backend/app/workflows/regression_run.py for the Temporal test server).
// Using the system font stack instead rather than silently fighting the
// build — a real deployment target with normal internet access can swap
// this back to next/font/google with no other changes.
export const metadata: Metadata = {
  title: "Agent Regression Flywheel",
  description:
    "Mines production agent failures into regression tasks and gates version promotion behind McNemar's exact test.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-neutral-950 text-neutral-200 font-sans">
        <Nav />
        {children}
      </body>
    </html>
  );
}
