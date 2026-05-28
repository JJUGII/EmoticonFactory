import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "이모티콘 스튜디오",
  description: "사진으로 나만의 이모티콘 만들기",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
