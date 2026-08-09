import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import localFont from "next/font/local";
import Script from "next/dist/client/script";

import "./globals.css";

const notoSansKhmer = localFont({
  src: [
    {
      path: "../fonts/NotoSansKhmer-Regular.woff2",
      weight: "400",
      style: "normal",
    },
    {
      path: "../fonts/NotoSansKhmer-Medium.woff2",
      weight: "500",
      style: "normal",
    },
    {
      path: "../fonts/NotoSansKhmer-SemiBold.woff2",
      weight: "600",
      style: "normal",
    },
    {
      path: "../fonts/NotoSansKhmer-Bold.woff2",
      weight: "700",
      style: "normal",
    },
    {
      path: "../fonts/NotoSansKhmer-ExtraBold.woff2",
      weight: "800",
      style: "normal",
    },
  ],
  variable: "--font-khmer",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Qauntify — Smart signals. Calmer trading.",
  description:
    "ការរៀបចំបច្ចេកទេសលើ crypto មាស និង forex — បញ្ជាក់ដោយ AI ពន្យល់ជាភាសាសាមញ្ញ។ Signals សម្រាប់ការអប់រំ និងវិភាគ — មិនមែនជាដំបូន្មានហិរញ្ញវត្ថុ។",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="km"
      suppressHydrationWarning
      className={`${notoSansKhmer.variable} ${jetbrains.variable} h-full antialiased`}
    >
      <head>
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
