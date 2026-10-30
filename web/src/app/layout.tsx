import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Hỏi đáp Luật Đất đai",
  description:
    "Hỏi đáp về pháp luật đất đai Việt Nam, trả lời kèm trích dẫn Điều, khoản của Luật Đất đai 2013.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-background text-foreground">{children}</body>
    </html>
  );
}
