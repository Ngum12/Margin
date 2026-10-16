/** The two page margins form an open book and an M. Drawn for Margin. */
export function Brand() {
  return (
    <span className="brand-lockup">
      <svg viewBox="0 0 40 40" fill="none" aria-hidden="true" className="brand-symbol">
        <path
          d="M7 30V10l13 8 13-8v20M13 13v13l7 4 7-4V13M20 18v12"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
        />
      </svg>
      <span>
        margin<span className="brand-period">.</span>
      </span>
    </span>
  );
}
