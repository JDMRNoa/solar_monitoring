export default function Footer() {
  return (
    <footer
      style={{ borderTop: '1px solid var(--border)', color: 'var(--text-dim)', fontSize: '0.65rem' }}
      className="mt-auto py-4 text-center"
    >
      SOLAR MONITORING SYSTEM · POWERED BY FASTAPI + ML · {new Date().getFullYear()}
    </footer>
  )
}
