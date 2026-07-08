import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MUSE 회의실",
  description: "AI 창작 조직 MUSE의 회의실 UI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
