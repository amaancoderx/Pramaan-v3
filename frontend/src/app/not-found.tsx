import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-line bg-surface px-6 py-12 text-center">
      <p className="text-sm font-semibold text-ink">Page not found</p>
      <p className="mt-1 text-sm text-muted">The page you are looking for does not exist.</p>
      <Link href="/" className="mt-4 inline-flex h-11 items-center rounded-xl bg-ink px-4 text-sm font-medium text-white">
        Go to Pramaan
      </Link>
    </div>
  );
}
