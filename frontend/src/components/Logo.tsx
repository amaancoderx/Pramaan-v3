export function LogoMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#0E1A2B" />
      <path d="M16 6.5 24.5 9v7.2c0 4.6-3.6 8.2-8.5 9.8-4.9-1.6-8.5-5.2-8.5-9.8V9L16 6.5Z" fill="#F6F4EF" />
      <path d="m12.2 15.8 2.7 2.7 5-5.4" fill="none" stroke="#12A594" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
