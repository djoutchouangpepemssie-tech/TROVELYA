import { DemoLink } from "./DemoLink";

/** The mock-up's site footer (WebHome). */
export function DemoFooter() {
  return (
    <footer style={{ borderTop: "0.5px solid rgba(60,60,67,0.16)", background: "#F5F5F8" }}>
      <div
        className="wrap"
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 16,
          minHeight: 72,
          fontSize: 13,
          color: "#6E6E73",
        }}
      >
        <span>© 2026 TROVÉLYA · La belle trouvaille</span>
        <span style={{ display: "flex", flexWrap: "wrap", gap: 20 }}>
          <DemoLink to="Dispute" style={{ color: "#6E6E73" }}>
            Aide et litiges
          </DemoLink>
          <DemoLink to="Menu" style={{ color: "#6E6E73" }}>
            Tout TROVÉLYA
          </DemoLink>
          <span>Français · 24 langues · EUR</span>
        </span>
      </div>
    </footer>
  );
}
