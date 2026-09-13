import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "JobPilot",
  description: "Safety-first autonomous job-application platform.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-[var(--border)]">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              JobPilot
            </Link>
            <nav className="flex items-center gap-4 text-sm">
              <Link
                href="/search"
                className="text-[var(--muted)] hover:text-[var(--text)]"
              >
                Search
              </Link>
              <Link
                href="/queue"
                className="text-[var(--muted)] hover:text-[var(--text)]"
              >
                Queue
              </Link>
              <a
                href="https://github.com/sairam782/jobpilot"
                target="_blank"
                rel="noreferrer noopener"
                className="text-[var(--muted)] hover:text-[var(--text)]"
              >
                GitHub ↗
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
