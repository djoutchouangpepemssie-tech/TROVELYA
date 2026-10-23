/** TROVÉLYA monogram (section 6.2): white "T" in a rounded brand-blue square. */
export function Logo({ label, size = 48 }: { label: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" role="img" aria-label={label}>
      <rect width="24" height="24" rx="6" fill="var(--trv-color-brand)" />
      <path d="M4.5 4h15v3.8h-5.6V20.5h-3.8V7.8H4.5z" fill="#FFFFFF" />
    </svg>
  );
}
