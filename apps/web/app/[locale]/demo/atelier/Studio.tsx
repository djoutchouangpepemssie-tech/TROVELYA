"use client";

import "./studio.css";

import Link from "next/link";
import { useState, type CSSProperties } from "react";

import { IMG } from "../_components/data";
import { DemoLink } from "../_components/DemoLink";

type Period = {
  rev: string;
  revD: string;
  ord: string;
  ordD: string;
  conv: string;
  share: string;
  x: [string, string, string, string];
};

const PERIODS: [Period, Period, Period] = [
  {
    rev: "4 210 €",
    revD: "+9 % vs semaine passée",
    ord: "49",
    ordD: "+6",
    conv: "3,4 %",
    share: "43 %",
    x: ["ven.", "dim.", "mar.", "jeu."],
  },
  {
    rev: "18 420 €",
    revD: "+18 % vs mois dernier",
    ord: "214",
    ordD: "+31",
    conv: "3,1 %",
    share: "46 %",
    x: ["24 sept.", "2 oct.", "12 oct.", "23 oct."],
  },
  {
    rev: "196 300 €",
    revD: "+64 % sur un an",
    ord: "2 380",
    ordD: "+910",
    conv: "2,9 %",
    share: "44 %",
    x: ["nov.", "févr.", "juin", "oct."],
  },
];

type PeriodIndex = 0 | 1 | 2;

const PERIOD_OPTIONS: { label: string; value: PeriodIndex }[] = [
  { label: "7 jours", value: 0 },
  { label: "30 jours", value: 1 },
  { label: "12 mois", value: 2 },
];

type Status = "À préparer" | "Livrée" | "En séquestre";

type Order = { id: string; c: string; ch: string; st: Status; a: string; t: 1 | 2 };

const ORDERS: Order[] = [
  { id: "AGO-48213", c: "Lucie M.", ch: "Fil Découvrir", st: "À préparer", a: "163,00 €", t: 1 },
  { id: "AGO-48207", c: "Karim B.", ch: "Live", st: "À préparer", a: "95,00 €", t: 1 },
  { id: "AGO-48199", c: "Sophie L.", ch: "Votre boutique", st: "Livrée", a: "240,00 €", t: 2 },
  { id: "AGO-48188", c: "Thomas R.", ch: "Enchère", st: "En séquestre", a: "410,00 €", t: 1 },
  { id: "AGO-48170", c: "Inès D.", ch: "Votre boutique", st: "Livrée", a: "68,00 €", t: 2 },
];

type FilterIndex = 0 | 1 | 2;

const FILTER_OPTIONS: { label: string; value: FilterIndex }[] = [
  { label: "Toutes", value: 0 },
  { label: "À préparer", value: 1 },
  { label: "Terminées", value: 2 },
];

const STATUS_STYLE: Record<Status, CSSProperties> = {
  Livrée: { background: "rgba(30,122,69,0.1)", color: "#155C33" },
  "En séquestre": { background: "rgba(29,43,255,0.08)", color: "#1420C8" },
  "À préparer": { background: "#FFF4D6", color: "#6B4B00" },
};

/** Sidebar entries after « Accueil » (the current screen), by mock-up target screen. */
const NAV: { to: string; label: string; count?: number }[] = [
  { to: "Order", label: "Commandes", count: 3 },
  { to: "Sell", label: "Produits" },
  { to: "Live", label: "Lives" },
  { to: "Auction", label: "Enchères" },
  { to: "Messages", label: "Clients et messages", count: 2 },
  { to: "Boost", label: "Marketing et TROVÉLYA Ads" },
  { to: "Studio", label: "Analytique" },
  { to: "Shop", label: "Vitrine et templates" },
  { to: "Shop", label: "Domaines et e-mails" },
  { to: "Profile", label: "Paramètres" },
];

const SOURCES = [
  { label: "Votre boutique", pct: 54, color: "#0B0B0F" },
  { label: "Fil Découvrir", pct: 21, color: "#1D2BFF" },
  { label: "Lives", pct: 14, color: "#1D2BFF" },
  { label: "Enchères", pct: 11, color: "#1D2BFF" },
];

const segmentGroup: CSSProperties = {
  display: "flex",
  gap: 2,
  padding: 3,
  borderRadius: 999,
  background: "rgba(118,118,128,0.12)",
};

const h2: CSSProperties = { margin: 0, fontSize: 17, fontWeight: 600 };

const sg = (on: boolean) => (on ? "sg on" : "sg");

/** Seller back office (mock-up WebStudio): period switch on the KPIs, filter on the orders. */
export function Studio() {
  const [p, setP] = useState<PeriodIndex>(1);
  const [f, setF] = useState<FilterIndex>(0);
  const d = PERIODS[p];
  const orders = ORDERS.filter((o) => f === 0 || o.t === f);

  return (
    <div
      className="demo-studio"
      style={{
        width: "100%",
        minHeight: 900,
        display: "flex",
        flexWrap: "wrap",
        background: "#F5F5F8",
        fontFamily: "var(--demo-sans)",
        color: "#0B0B0F",
        WebkitFontSmoothing: "antialiased",
      }}
    >
      <aside
        style={{
          flex: "1 1 240px",
          background: "#0B0B0F",
          color: "#FFFFFF",
          padding: "22px 14px",
          boxSizing: "border-box",
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "0 12px 18px" }}>
          <Link
            href="/fr/demo"
            style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.04em", color: "inherit" }}
          >
            TROVÉLYA
          </Link>
          <span style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>Atelier</span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 12px",
            marginBottom: 10,
            borderRadius: 12,
            background: "rgba(255,255,255,0.06)",
          }}
        >
          <span
            style={{
              width: 30,
              height: 30,
              borderRadius: 9,
              background: "#FFFFFF",
              color: "#0B0B0F",
              display: "grid",
              placeItems: "center",
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            AO
          </span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Atelier Opaline</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)" }}>atelier-opaline.fr</div>
          </div>
        </div>
        <Link href="/fr/demo/atelier" className="nav on" aria-current="page">
          Accueil
        </Link>
        {NAV.map((n) => (
          <DemoLink key={n.label} to={n.to} className="nav">
            {n.label}
            {n.count !== undefined && <span className="n">{n.count}</span>}
          </DemoLink>
        ))}
        <div
          style={{
            marginTop: "auto",
            padding: "14px 12px",
            borderRadius: 14,
            background: "rgba(255,255,255,0.06)",
          }}
        >
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)" }}>Solde disponible</div>
          <div className="m" style={{ fontSize: 22, letterSpacing: "-0.03em", marginTop: 2 }}>
            1 840,50 €
          </div>
          <button
            type="button"
            className="btn"
            style={{
              marginTop: 10,
              height: 34,
              background: "#FFFFFF",
              color: "#0B0B0F",
              fontSize: 13,
            }}
          >
            Virer sur mon compte
          </button>
        </div>
      </aside>

      <main
        className="demo-studio-main"
        style={{
          flex: "999 1 560px",
          minWidth: 0,
          padding: "28px 32px 40px",
          boxSizing: "border-box",
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 16,
            alignItems: "flex-end",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div style={{ fontSize: 14, color: "#6E6E73" }}>Vendredi 23 octobre</div>
            <h1
              style={{
                margin: "2px 0 0",
                fontSize: 30,
                fontWeight: 700,
                letterSpacing: "-0.035em",
              }}
            >
              Bonjour Arcel
            </h1>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <div style={segmentGroup} role="group" aria-label="Période">
              {PERIOD_OPTIONS.map(({ label, value }) => (
                <button
                  key={label}
                  type="button"
                  className={sg(p === value)}
                  aria-pressed={p === value}
                  onClick={() => {
                    setP(value);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <DemoLink to="Live" className="btn" style={{ background: "#0B0B0F", color: "#FFFFFF" }}>
              <span
                style={{ width: 7, height: 7, borderRadius: "50%", background: "#D93026" }}
              ></span>
              Lancer un live
            </DemoLink>
            <DemoLink to="Sell" className="btn" style={{ background: "#1D2BFF", color: "#FFFFFF" }}>
              Ajouter un produit
            </DemoLink>
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: 16,
          }}
        >
          <div className="card">
            <div className="kl">Chiffre d&apos;affaires</div>
            <div className="kv">{d.rev}</div>
            <div className="kd">{d.revD}</div>
          </div>
          <div className="card">
            <div className="kl">Commandes</div>
            <div className="kv">{d.ord}</div>
            <div className="kd">{d.ordD}</div>
          </div>
          <div className="card">
            <div className="kl">Taux de conversion</div>
            <div className="kv">{d.conv}</div>
            <div className="kd">+0,4 point</div>
          </div>
          <div className="card">
            <div className="kl">Ventes apportées par TROVÉLYA</div>
            <div className="kv">{d.share}</div>
            <div style={{ fontSize: 13, color: "#6E6E73", marginTop: 2 }}>
              fil, live, enchères, recherche
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
          <div className="card" style={{ flex: "2 1 520px" }}>
            <div
              style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}
            >
              <h2 style={h2}>Ventes</h2>
              <div style={{ display: "flex", gap: 16, fontSize: 12, color: "#6E6E73" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{ width: 10, height: 10, borderRadius: 3, background: "#1D2BFF" }}
                  ></span>
                  Total
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: 3,
                      background: "rgba(29,43,255,0.25)",
                    }}
                  ></span>
                  Apportées par TROVÉLYA
                </span>
              </div>
            </div>
            <svg
              role="img"
              aria-label="Courbe des ventes, en hausse"
              width="100%"
              height="220"
              viewBox="0 0 700 220"
              preserveAspectRatio="none"
              style={{ display: "block", marginTop: 14 }}
            >
              <g stroke="rgba(60,60,67,0.1)">
                <line x1="0" y1="20" x2="700" y2="20" />
                <line x1="0" y1="85" x2="700" y2="85" />
                <line x1="0" y1="150" x2="700" y2="150" />
                <line x1="0" y1="215" x2="700" y2="215" />
              </g>
              <path
                d="M0 170 C 60 165, 90 150, 140 152 S 230 120, 280 126 S 380 96, 430 90 S 540 60, 590 52 S 660 34, 700 28 L 700 215 L 0 215 Z"
                fill="rgba(29,43,255,0.07)"
              />
              <path
                d="M0 192 C 70 190, 110 182, 160 180 S 260 165, 310 160 S 410 140, 460 136 S 580 116, 640 108 S 680 104, 700 100"
                fill="none"
                stroke="rgba(29,43,255,0.35)"
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
              <path
                d="M0 170 C 60 165, 90 150, 140 152 S 230 120, 280 126 S 380 96, 430 90 S 540 60, 590 52 S 660 34, 700 28"
                fill="none"
                stroke="#1D2BFF"
                strokeWidth="2.5"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 12,
                color: "#6E6E73",
                marginTop: 6,
              }}
            >
              {d.x.map((x) => (
                <span key={x}>{x}</span>
              ))}
            </div>
          </div>
          <div
            className="card"
            style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: 14 }}
          >
            <h2 style={h2}>D&apos;où viennent vos ventes</h2>
            {SOURCES.map((s) => (
              <div key={s.label}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: 14,
                    marginBottom: 6,
                  }}
                >
                  <span>{s.label}</span>
                  <span className="m">{s.pct} %</span>
                </div>
                <div className="bar">
                  <div style={{ width: `${String(s.pct)}%`, background: s.color }}></div>
                </div>
              </div>
            ))}
            <div style={{ fontSize: 13, color: "#6E6E73" }}>
              Aucune commission sur les ventes de votre boutique.
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
          <div className="card" style={{ flex: "2 1 520px" }}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 12,
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 14,
              }}
            >
              <h2 style={h2}>Commandes récentes</h2>
              <div style={segmentGroup} role="group" aria-label="Filtrer les commandes">
                {FILTER_OPTIONS.map(({ label, value }) => (
                  <button
                    key={label}
                    type="button"
                    className={sg(f === value)}
                    aria-pressed={f === value}
                    onClick={() => {
                      setF(value);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Commande</th>
                    <th scope="col">Client</th>
                    <th scope="col">Canal</th>
                    <th scope="col">Statut</th>
                    <th scope="col" style={{ textAlign: "right" }}>
                      Montant
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.id}>
                      <td className="m" style={{ fontSize: 13 }}>
                        {o.id}
                      </td>
                      <td>{o.c}</td>
                      <td style={{ color: "#6E6E73" }}>{o.ch}</td>
                      <td>
                        <span className="st" style={STATUS_STYLE[o.st]}>
                          {o.st}
                        </span>
                      </td>
                      <td className="m" style={{ textAlign: "right" }}>
                        {o.a}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div
            style={{
              flex: "1 1 280px",
              display: "flex",
              flexDirection: "column",
              gap: 16,
              minWidth: 0,
            }}
          >
            <div className="card" style={{ background: "#0B0B0F", color: "#FFFFFF" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  color: "rgba(255,255,255,0.75)",
                }}
              >
                <svg
                  aria-hidden="true"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 3.5l1.6 4.4L18 9.5l-4.4 1.6L12 15.5l-1.6-4.4L6 9.5l4.4-1.6z" />
                </svg>
                Analyste IA
              </div>
              <div style={{ fontSize: 15, lineHeight: 1.45, marginTop: 10 }}>
                Vos ventes ont baissé mardi parce que la lampe la plus vue était en rupture.
                Remettez 3 pièces en stock : environ 280 € de ventes récupérables cette semaine.
              </div>
              <button
                type="button"
                className="btn"
                style={{
                  marginTop: 14,
                  height: 36,
                  background: "#FFFFFF",
                  color: "#0B0B0F",
                  fontSize: 13,
                }}
              >
                Réapprovisionner
              </button>
            </div>
            <DemoLink
              to="Shop"
              className="card"
              style={{
                display: "flex",
                gap: 14,
                alignItems: "center",
                textDecoration: "none",
                color: "#0B0B0F",
              }}
            >
              <img
                src={IMG.lamp}
                alt=""
                style={{ width: 72, height: 72, borderRadius: 14, objectFit: "cover" }}
              />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600 }}>Votre vitrine</div>
                <div style={{ fontSize: 13, color: "#6E6E73" }}>
                  atelier-opaline.fr · thème Opaline
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1D2BFF", marginTop: 4 }}>
                  Personnaliser
                </div>
              </div>
            </DemoLink>
          </div>
        </div>
      </main>
    </div>
  );
}
