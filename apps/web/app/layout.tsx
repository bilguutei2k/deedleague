import "./globals.css";
import Link from "next/link";

export const metadata = {
  title: "Deed League Index",
  description: "Analytics for Mongolia's Үндэсний Дээд Лиг (men's).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="mn">
      <body className="bg-white text-gray-900 antialiased">
        <header className="border-b border-gray-200">
          <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
            <Link href="/" className="font-semibold">
              Deed League Index
            </Link>
            <nav className="flex gap-3 text-sm text-gray-600">
              <Link href="/">Home</Link>
              <Link href="/leaders">Leaders</Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-5xl px-4 py-8 text-xs text-gray-400">
          Read-only analytics. Source: msports.
        </footer>
      </body>
    </html>
  );
}
