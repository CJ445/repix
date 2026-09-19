/** Repix mark: an original/result split. Decorative; the wordmark next to it names the app. */
export default function Logo({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <defs>
        <clipPath id="repix-tile">
          <rect width="32" height="32" rx="7" />
        </clipPath>
      </defs>
      <g clipPath="url(#repix-tile)">
        <rect width="32" height="32" fill="#4b4b55" />
        <rect x="16" width="16" height="32" fill="#0b6e69" />
        <rect x="15" width="2" height="32" fill="#fff" />
      </g>
      <circle cx="16" cy="16" r="5" fill="#fff" />
    </svg>
  )
}
