"use client";

import "./home.css";

import { useState } from "react";

import { IMG, type ImageKey } from "./_components/data";
import { DemoFooter } from "./_components/DemoFooter";
import { DemoHeader } from "./_components/DemoHeader";
import { DemoLink } from "./_components/DemoLink";
import { badgeStyle, HeartIcon, VerifiedIcon } from "./_components/icons";

type Item = {
  t: string;
  p: string;
  img: ImageKey;
  b: string;
  k: "auc" | "buy" | "live";
  where: string;
  v: boolean;
  to: string;
};

// The mock-up's feed (WebHome).
const P: Item[] = [
  {
    t: "Montre automatique, 1968",
    p: "1 240 €",
    img: "watch",
    b: "Enchère · 02:14",
    k: "auc",
    where: "Paris 11e · 1,2 km",
    v: true,
    to: "Auction",
  },
  {
    t: "Les Fleurs du mal, 1857",
    p: "18 500 €",
    img: "book",
    b: "Achat immédiat",
    k: "buy",
    where: "Librairie du Vieux-Lyon · Lyon 5e",
    v: true,
    to: "WebProduct",
  },
  {
    t: "Lampe champignon opaline",
    p: "95 €",
    img: "lamp",
    b: "Achat immédiat",
    k: "buy",
    where: "Paris 11e · 0,8 km",
    v: true,
    to: "WebProduct",
  },
  {
    t: "Lot de vinyles soul, 1972",
    p: "46 €",
    img: "vinyl",
    b: "En live",
    k: "live",
    where: "Le Grenier de Lyon",
    v: true,
    to: "WebLive",
  },
  {
    t: "Objectif 50 mm f/1.4",
    p: "420 €",
    img: "lens",
    b: "Enchère · 08:41",
    k: "auc",
    where: "Montreuil · 4,1 km",
    v: false,
    to: "Auction",
  },
  {
    t: "Vase en grès émaillé",
    p: "64 €",
    img: "vase",
    b: "Achat immédiat",
    k: "buy",
    where: "Paris 20e · 2,4 km",
    v: false,
    to: "WebProduct",
  },
];
const ORDERS = [
  [0, 1, 2, 3, 4, 5],
  [2, 0, 5, 4, 3, 1],
  [3, 1, 2, 0, 5, 4],
] as const;
const TABS = ["Pour toi", "Près de moi", "Abonnements"] as const;
const TITLES = ["Choisi pour vous", "Près de chez vous", "Vos vendeurs suivis"] as const;

const UNIVERSES: [ImageKey, string][] = [
  ["watch", "Montres"],
  ["vinyl", "Musique"],
  ["book", "Livres rares"],
  ["lamp", "Maison"],
  ["lens", "Photo"],
  ["vase", "Céramique"],
];

const TRUST = [
  {
    title: "Argent protégé",
    text: "Payé au vendeur seulement quand vous avez l'objet.",
    gradient: "linear-gradient(155deg, #5866FF, #1420C8)",
    icon: (
      <path
        d="M12 2.8 4.6 5.8v6.1c0 4.6 3.1 7.8 7.4 9.3 4.3-1.5 7.4-4.7 7.4-9.3V5.8z"
        fill="#FFFFFF"
      />
    ),
  },
  {
    title: "Passeport produit",
    text: "Origine, propriétaires et prix de chaque objet.",
    gradient: "linear-gradient(155deg, #3EDBC9, #0A8794)",
    icon: (
      <>
        <rect x="4" y="5" width="16" height="14" rx="3" fill="#FFFFFF" />
        <path d="M8 12h8M8 15.5h5" stroke="#0A8794" strokeWidth="1.8" strokeLinecap="round" />
      </>
    ),
  },
  {
    title: "Remise en main propre",
    text: "Un code à donner au vendeur, et c'est réglé.",
    gradient: "linear-gradient(155deg, #FFB24A, #C2540A)",
    icon: (
      <path d="M12 21s-6.6-5.5-6.6-11a6.6 6.6 0 0 1 13.2 0c0 5.5-6.6 11-6.6 11z" fill="#FFFFFF" />
    ),
  },
  {
    title: "Valeur de revente",
    text: "Vos objets gardent une cote, visible à tout moment.",
    gradient: "linear-gradient(155deg, #3EDB86, #0F7F45)",
    icon: (
      <path
        d="M3.5 17 8.5 11.5l4 3 8-8.5"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
];

const h2 = { margin: 0, fontSize: 28, fontWeight: 700, letterSpacing: "-0.035em" } as const;

/** Mock-up screen WebHome. */
export function Home() {
  const [tab, setTab] = useState<0 | 1 | 2>(0);
  const [fav, setFav] = useState<Record<number, boolean>>({});

  function toggle(index: number) {
    setFav((current) => ({ ...current, [index]: !current[index] }));
  }

  return (
    <div className="demo-home">
      <DemoHeader mega />

      <main
        className="wrap"
        style={{
          paddingTop: 28,
          paddingBottom: 56,
          display: "flex",
          flexDirection: "column",
          gap: 44,
        }}
      >
        <h1 className="sr-only">TROVÉLYA, la belle trouvaille</h1>
        {/* Bandeau principal */}
        <section
          className="home-hero"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1.9fr) minmax(0, 1fr)",
            gap: 16,
          }}
        >
          <DemoLink
            to="WebLive"
            style={{
              position: "relative",
              borderRadius: 28,
              overflow: "hidden",
              minHeight: 420,
              display: "block",
              color: "#FFFFFF",
              background: "#0B0B0F",
            }}
          >
            <img
              src={IMG.liveVinyls}
              alt="Live : un vendeur présente un disque vinyle"
              style={{
                position: "absolute",
                top: 0,
                right: 0,
                bottom: 0,
                width: "64%",
                height: "100%",
                objectFit: "cover",
                objectPosition: "50% 42%",
              }}
            />
            <span
              style={{
                position: "absolute",
                inset: 0,
                background:
                  "linear-gradient(90deg, #0B0B0F 0%, #0B0B0F 34%, rgba(11,11,15,0.55) 48%, rgba(11,11,15,0) 66%)",
              }}
            />
            <span
              style={{
                position: "absolute",
                left: 36,
                top: 34,
                display: "flex",
                gap: 8,
                alignItems: "center",
              }}
            >
              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  background: "#D93026",
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: "0.06em",
                  padding: "6px 11px 6px 9px",
                  borderRadius: 999,
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#FFFFFF" }} />
                EN DIRECT
              </span>
              <span
                className="lg lg-dark"
                style={{ fontSize: 13, fontWeight: 600, padding: "6px 11px", borderRadius: 999 }}
              >
                1 284 spectateurs
              </span>
            </span>
            <span style={{ position: "absolute", left: 36, right: 24, bottom: 36, maxWidth: 460 }}>
              <span style={{ display: "block", fontSize: 14, fontWeight: 500, opacity: 0.85 }}>
                Le Grenier de Lyon · Rang Or
              </span>
              <span
                className="home-hero-title"
                style={{
                  display: "block",
                  fontSize: 46,
                  fontWeight: 700,
                  letterSpacing: "-0.04em",
                  lineHeight: 1.02,
                  marginTop: 6,
                }}
              >
                Vinyles rares,
                <br />
                années 70
              </span>
              <span
                className="home-hero-cta"
                style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 22 }}
              >
                <span className="btnp" style={{ height: 48, padding: "0 22px", fontSize: 15 }}>
                  Rejoindre le live
                </span>
                <span
                  className="lg lg-dark"
                  style={{
                    height: 48,
                    padding: "0 18px",
                    borderRadius: 999,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: 14,
                    fontWeight: 600,
                  }}
                >
                  Enchère en cours <span className="m">46 €</span>
                </span>
              </span>
            </span>
          </DemoLink>
          <div
            className="home-hero-side"
            style={{ display: "grid", gridTemplateRows: "1fr 1fr", gap: 16 }}
          >
            <DemoLink
              to="Auction"
              style={{
                position: "relative",
                borderRadius: 28,
                overflow: "hidden",
                display: "block",
                color: "#FFFFFF",
                background: "#0B0B0F",
              }}
            >
              <img
                src={IMG.watch}
                alt="Montre automatique de 1968"
                style={{
                  position: "absolute",
                  inset: 0,
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                }}
              />
              <span
                style={{
                  position: "absolute",
                  inset: 0,
                  background: "linear-gradient(180deg, rgba(0,0,0,0) 35%, rgba(0,0,0,0.6))",
                }}
              />
              <span
                className="lg lg-dark m"
                style={{
                  position: "absolute",
                  top: 18,
                  left: 18,
                  fontSize: 14,
                  padding: "6px 11px",
                  borderRadius: 999,
                }}
              >
                02:14
              </span>
              <span style={{ position: "absolute", left: 22, right: 22, bottom: 18 }}>
                <span style={{ display: "block", fontSize: 13, opacity: 0.85 }}>
                  Enchère · se termine bientôt
                </span>
                <span
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    gap: 12,
                    marginTop: 2,
                  }}
                >
                  <span style={{ fontSize: 21, fontWeight: 600, letterSpacing: "-0.02em" }}>
                    Montre automatique, 1968
                  </span>
                  <span className="m" style={{ fontSize: 20, whiteSpace: "nowrap" }}>
                    1 240 €
                  </span>
                </span>
              </span>
            </DemoLink>
            <DemoLink
              to="Search"
              style={{
                position: "relative",
                borderRadius: 28,
                overflow: "hidden",
                display: "block",
                color: "#0B0B0F",
                background: "#EEF0FF",
              }}
            >
              <img
                src={IMG.map}
                alt="Carte du quartier"
                style={{
                  position: "absolute",
                  inset: 0,
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  opacity: 0.9,
                  transform: "scale(1.6)",
                  transformOrigin: "100% 0%",
                }}
              />
              <span
                className="lg"
                style={{
                  position: "absolute",
                  left: 18,
                  right: 18,
                  bottom: 18,
                  borderRadius: 20,
                  padding: "14px 16px",
                  background: "rgba(255,255,255,0.78)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <span>
                  <span
                    style={{
                      display: "block",
                      fontSize: 17,
                      fontWeight: 600,
                      letterSpacing: "-0.02em",
                    }}
                  >
                    482 objets à moins de 5 km
                  </span>
                  <span style={{ display: "block", fontSize: 13, color: "#6E6E73", marginTop: 2 }}>
                    Remise en main propre protégée, aujourd&apos;hui
                  </span>
                </span>
                <span
                  style={{
                    width: 40,
                    height: 40,
                    flex: "none",
                    borderRadius: "50%",
                    background: "#1D2BFF",
                    display: "grid",
                    placeItems: "center",
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="m9 5 7 7-7 7" />
                  </svg>
                </span>
              </span>
            </DemoLink>
          </div>
        </section>

        {/* Fil */}
        <section aria-labelledby="feed-title">
          <div
            className="home-feed-head"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 16,
              marginBottom: 18,
            }}
          >
            <h2 id="feed-title" style={h2}>
              {TITLES[tab]}
            </h2>
            <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
              {TABS.map((label, i) => (
                <button
                  key={label}
                  type="button"
                  className={tab === i ? "tab on" : "tab"}
                  aria-pressed={tab === i}
                  onClick={() => {
                    setTab(i as 0 | 1 | 2);
                  }}
                >
                  {label}
                </button>
              ))}
              <DemoLink to="WebCatalog" style={{ marginLeft: 12, fontSize: 15, fontWeight: 600 }}>
                Tout voir
              </DemoLink>
            </div>
          </div>
          <div
            className="home-grid6"
            style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(0, 1fr))", gap: 18 }}
          >
            {ORDERS[tab].map((i) => {
              const p = P[i];
              if (!p) return null;
              const on = Boolean(fav[i]);
              return (
                <div key={p.t} className="pc-card">
                  <DemoLink to={p.to} className="pc">
                    <span className="im">
                      <img src={IMG[p.img]} alt={p.t} />
                      <span className="bdg" style={badgeStyle(p.k)}>
                        {p.b}
                      </span>
                    </span>
                    <span>
                      <span
                        style={{
                          display: "block",
                          fontSize: 14,
                          fontWeight: 500,
                          color: "#3A3A3F",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {p.t}
                      </span>
                      <span className="m" style={{ display: "block", fontSize: 17, marginTop: 2 }}>
                        {p.p}
                      </span>
                      <span
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 5,
                          fontSize: 12,
                          color: "#6E6E73",
                          marginTop: 3,
                        }}
                      >
                        {p.where}
                        <VerifiedIcon hidden={!p.v} />
                      </span>
                    </span>
                  </DemoLink>
                  <button
                    type="button"
                    className="fav lg"
                    aria-label="Ajouter aux favoris"
                    aria-pressed={on}
                    style={{ background: "rgba(255,255,255,0.75)" }}
                    onClick={() => {
                      toggle(i);
                    }}
                  >
                    <HeartIcon on={on} />
                  </button>
                </div>
              );
            })}
          </div>
        </section>

        {/* Univers */}
        <section aria-labelledby="universes-title">
          <h2 id="universes-title" style={{ ...h2, margin: "0 0 18px" }}>
            Explorer par univers
          </h2>
          <div
            className="home-grid6"
            style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(0, 1fr))", gap: 14 }}
          >
            {UNIVERSES.map(([img, name]) => (
              <DemoLink key={name} to="WebCatalog" className="uni">
                <img src={IMG[img]} alt="" />
                <span>{name}</span>
              </DemoLink>
            ))}
          </div>
        </section>

        {/* Confiance */}
        <section
          className="home-grid4"
          aria-label="Nos garanties"
          style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 14 }}
        >
          {TRUST.map((item) => (
            <div key={item.title} style={{ padding: 22, borderRadius: 22, background: "#F5F5F8" }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 12,
                  background: item.gradient,
                  display: "grid",
                  placeItems: "center",
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                  {item.icon}
                </svg>
              </div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 14 }}>{item.title}</div>
              <div style={{ fontSize: 14, color: "#6E6E73", marginTop: 4, lineHeight: 1.45 }}>
                {item.text}
              </div>
            </div>
          ))}
        </section>
      </main>

      <DemoFooter />
    </div>
  );
}
