import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/manrope";
import "./globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "c0ntr0l | Runtime operations",
  description: "Runtime visibility and policy control for AI applications.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
