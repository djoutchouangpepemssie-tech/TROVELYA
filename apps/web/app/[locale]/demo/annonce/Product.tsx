"use client";

import "./product.css";

import { type CSSProperties, type KeyboardEvent, useRef, useState } from "react";

import { DemoHeader } from "../_components/DemoHeader";
import { DemoLink } from "../_components/DemoLink";
import { IMG } from "../_components/data";
import { euros } from "../_components/icons";

const PRICE = 18500;
const PROTECTION = 150;

const COVER: CSSProperties = { width: "100%", height: "100%", objectFit: "cover" };

// Gallery views: one photo, cropped differently (the last one stands for the verification video).
type View = [name: string, crop: CSSProperties];
const FIRST: View = ["Couverture", COVER];
const VIEWS: View[] = [
  FIRST,
  ["Titre en détail", { ...COVER, transform: "scale(2.2)", transformOrigin: "50% 32%" }],
  ["Dos et reliure", { ...COVER, transform: "scale(2)", transformOrigin: "18% 55%" }],
  ["Date d’édition", { ...COVER, transform: "scale(2.4)", transformOrigin: "50% 80%" }],
  ["Vidéo de vérification", { ...COVER, filter: "brightness(0.7)" }],
];
const VIDEO = VIEWS.length - 1;

const DELIVERY: { t: string; d: string; fee: number }[] = [
  { t: "Remise en main propre", d: "Lyon 5e · paiement protégé, code au rendez-vous", fee: 0 },
  { t: "Envoi assuré", d: `Livré en 48 h · assuré pour ${euros(PRICE)}`, fee: 35 },
];

const OFFERS = [16500, 17200, 17800];

const TABS = ["Description", "Passeport produit", "Historique des prix"];

const PASSPORT: [string, string, string][] = [
  ["1857", "Impression à Alençon", "Poulet-Malassis et de Broise · tirage de 1 300 exemplaires"],
  ["1931", "Collection privée, Lyon", "Ex-libris apposé sur la garde"],
  ["1988", "Vente aux enchères, Paris", "Adjugé 41 000 francs"],
  ["2019", "Librairie du Vieux-Lyon", "Acquis lors d’une succession"],
  ["Oct. 2026", "Authentifié sur TROVÉLYA", "Expert partenaire · certificat AG-1857-0042"],
];

const SIMILAR: {
  to: string;
  src: string;
  alt: string;
  name: string;
  price: number;
  img?: CSSProperties;
}[] = [
  {
    to: "Auction",
    src: IMG.book,
    alt: "Les Fleurs du mal, réédition de 1868",
    name: "Les Fleurs du mal, réédition 1868",
    price: 240,
    img: { filter: "hue-rotate(-115deg) saturate(1.2)", transform: "scale(1.2)" },
  },
  {
    to: "WebProduct",
    src: IMG.lamp,
    alt: "Lampe champignon opaline",
    name: "Lampe champignon opaline",
    price: 95,
  },
  {
    to: "Auction",
    src: IMG.lens,
    alt: "Objectif 50 mm f/1.4",
    name: "Objectif 50 mm f/1.4",
    price: 420,
  },
  {
    to: "WebLive",
    src: IMG.vinyl,
    alt: "Lot de vinyles soul, 1972",
    name: "Lot de vinyles soul, 1972",
    price: 46,
  },
  {
    to: "Auction",
    src: IMG.watch,
    alt: "Montre automatique, 1968",
    name: "Montre automatique, 1968",
    price: 1240,
  },
];

const SANS = "var(--demo-sans)";
const GREY: CSSProperties = { background: "#F2F2F7", color: "#0B0B0F" };
const INK: CSSProperties = { background: "#0B0B0F", color: "#FFFFFF" };

/** The mock-up's product page (WebProduct). */
export function Product() {
  const [img, setImg] = useState(0);
  const [opt, setOpt] = useState(0);
  const [offer, setOffer] = useState(false);
  const [ov, setOv] = useState(1);
  const [sent, setSent] = useState(false);
  const [fav, setFav] = useState(false);
  const [alert, setAlert] = useState(false);
  const [follow, setFollow] = useState(false);
  const [tab, setTab] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const view = VIEWS[img] ?? FIRST;
  const total = PRICE + PROTECTION + (DELIVERY[opt]?.fee ?? 0);

  const onTabKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = (tab + step + TABS.length) % TABS.length;
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  return (
    <div
      className="demo-product"
      style={{
        width: "100%",
        minHeight: 1300,
        background: "#FFFFFF",
        fontFamily: SANS,
        color: "#0B0B0F",
        WebkitFontSmoothing: "antialiased",
        position: "relative",
      }}
    >
      <DemoHeader active="Livres" />

      <main className="wrap" style={{ paddingTop: 18, paddingBottom: 60 }}>
        <div style={{ fontSize: 13, color: "#6E6E73" }}>
          <DemoLink to="WebHome" style={{ color: "#6E6E73" }}>
            Accueil
          </DemoLink>{" "}
          ›{" "}
          <DemoLink to="WebCatalog" style={{ color: "#6E6E73" }}>
            Livres
          </DemoLink>{" "}
          ›{" "}
          <DemoLink to="WebCatalog" style={{ color: "#6E6E73" }}>
            Livres rares
          </DemoLink>{" "}
          › <span style={{ color: "#0B0B0F" }}>Éditions originales</span>
        </div>

        <div
          className="pd-cols"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)",
            gap: 48,
            marginTop: 16,
            alignItems: "start",
          }}
        >
          {/* Galerie */}
          <section className="pd-gallery" style={{ display: "flex", gap: 14 }}>
            <div
              className="pd-thumbs"
              style={{ display: "flex", flexDirection: "column", gap: 10 }}
            >
              {VIEWS.map(([name, crop], i) => (
                <button
                  key={name}
                  type="button"
                  className="th"
                  aria-label={name}
                  aria-pressed={img === i}
                  onClick={() => {
                    setImg(i);
                  }}
                  style={{
                    boxShadow:
                      img === i ? "0 0 0 2.5px #1D2BFF" : "inset 0 0 0 0.5px rgba(60,60,67,0.2)",
                  }}
                >
                  <img src={IMG.book} alt="" style={crop} />
                  <span
                    style={
                      i === VIDEO
                        ? { position: "absolute", inset: 0, display: "grid", placeItems: "center" }
                        : { display: "none" }
                    }
                  >
                    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                      <circle cx="12" cy="12" r="11" fill="rgba(11,11,15,0.6)" />
                      <path d="M10 8v8l6-4z" fill="#FFFFFF" />
                    </svg>
                  </span>
                </button>
              ))}
            </div>
            <div
              style={{
                position: "relative",
                flex: 1,
                aspectRatio: "1 / 1",
                borderRadius: 28,
                overflow: "hidden",
                background: "#F2F2F7",
              }}
            >
              <img
                src={IMG.book}
                alt="Les Fleurs du mal, édition originale de 1857, reliure toile verte"
                style={view[1]}
              />
              <span style={{ position: "absolute", left: 18, top: 18, display: "flex", gap: 8 }}>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    padding: "6px 10px",
                    borderRadius: 999,
                    background: "rgba(255,255,255,0.92)",
                  }}
                >
                  {view[0]}
                </span>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    padding: "6px 10px",
                    borderRadius: 999,
                    background: "#1D2BFF",
                    color: "#FFFFFF",
                  }}
                >
                  Authentifié par un expert
                </span>
              </span>
              <span
                style={
                  img === VIDEO
                    ? {
                        position: "absolute",
                        inset: 0,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                      }
                    : { display: "none" }
                }
              >
                <span
                  style={{
                    display: "grid",
                    placeItems: "center",
                    width: 76,
                    height: 76,
                    borderRadius: "50%",
                    background: "rgba(255,255,255,0.9)",
                    boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
                  }}
                >
                  <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M8 5v14l11-7z" fill="#0B0B0F" />
                  </svg>
                </span>
                <span
                  style={{
                    marginTop: 12,
                    fontSize: 14,
                    fontWeight: 600,
                    color: "#FFFFFF",
                    textShadow: "0 1px 8px rgba(0,0,0,0.5)",
                  }}
                >
                  Vidéo de vérification · 0:48 · filmée le 12 oct. 2026
                </span>
              </span>
            </div>
          </section>

          {/* Achat */}
          <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 14,
                  background: "#0B0B0F",
                  color: "#FFFFFF",
                  display: "grid",
                  placeItems: "center",
                  fontWeight: 600,
                }}
              >
                LV
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <DemoLink to="Shop" style={{ fontSize: 15, fontWeight: 600, color: "#0B0B0F" }}>
                  Librairie du Vieux-Lyon
                </DemoLink>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: 13,
                    color: "#6E6E73",
                    marginTop: 1,
                  }}
                >
                  <span
                    style={{
                      fontWeight: 600,
                      color: "#8A6A00",
                      background: "#FFF4D6",
                      padding: "1px 7px",
                      borderRadius: 999,
                      fontSize: 12,
                    }}
                  >
                    Rang Or
                  </span>
                  4,9 · 312 ventes · Lyon 5e
                </div>
              </div>
              <button
                type="button"
                className="sm"
                aria-pressed={follow}
                onClick={() => {
                  setFollow(!follow);
                }}
                style={follow ? GREY : INK}
              >
                {follow ? "Abonné" : "Suivre"}
              </button>
            </div>
            <h1
              style={{
                margin: "4px 0 0",
                fontSize: 34,
                fontWeight: 700,
                letterSpacing: "-0.04em",
                lineHeight: 1.08,
              }}
            >
              Les Fleurs du mal, édition originale de 1857
            </h1>
            <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
              <span className="m" style={{ fontSize: 36, letterSpacing: "-0.03em" }}>
                {euros(PRICE)}
              </span>
              <span style={{ fontSize: 15, color: "#6E6E73" }}>
                ou 4 × {euros(PRICE / 4)} sans frais
              </span>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "12px 14px",
                borderRadius: 16,
                background: "rgba(30,122,69,0.08)",
                color: "#155C33",
                fontSize: 14,
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M3.5 17 8.5 11.5l4 3 8-8.5"
                  fill="none"
                  stroke="#1E7A45"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>
                Valeur de revente estimée dans 1 an : <b className="m">{euros(19200)}</b> (+3,8 %)
              </span>
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 8,
                padding: 6,
                borderRadius: 20,
                background: "#F2F2F7",
              }}
              role="radiogroup"
              aria-label="Mode de remise"
            >
              {DELIVERY.map((o, i) => (
                <button
                  key={o.t}
                  type="button"
                  className="opt"
                  role="radio"
                  aria-checked={opt === i}
                  onClick={() => {
                    setOpt(i);
                  }}
                  style={
                    opt === i
                      ? { boxShadow: "0 2px 10px rgba(0,0,0,0.08)" }
                      : { background: "transparent" }
                  }
                >
                  <span
                    className="rad"
                    style={
                      opt === i
                        ? { border: "6px solid #1D2BFF" }
                        : { border: "1.5px solid #C7C7CC" }
                    }
                  />
                  <span style={{ flex: 1 }}>
                    <span style={{ display: "block", fontWeight: 600 }}>{o.t}</span>
                    <span
                      style={{ display: "block", fontSize: 13, color: "#6E6E73", marginTop: 1 }}
                    >
                      {o.d}
                    </span>
                  </span>
                  <span className="m" style={{ fontSize: 14 }}>
                    {o.fee === 0 ? "Gratuit" : euros(o.fee)}
                  </span>
                </button>
              ))}
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 14,
                color: "#3A3A3F",
                padding: "0 4px",
              }}
            >
              <span>Protection acheteur (plafonnée)</span>
              <span className="m">{euros(PROTECTION)}</span>
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 17,
                fontWeight: 600,
                padding: "0 4px",
              }}
            >
              <span>Total</span>
              <span className="m">{euros(total)}</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <DemoLink
                to="Checkout"
                className="btnp"
                style={{ height: 54, justifyContent: "center", fontSize: 16 }}
              >
                Acheter
              </DemoLink>
              <button
                type="button"
                aria-expanded={offer}
                onClick={() => {
                  setOffer(!offer);
                }}
                style={{
                  height: 54,
                  borderRadius: 999,
                  border: 0,
                  background: "#0B0B0F",
                  color: "#FFFFFF",
                  font: `600 16px ${SANS}`,
                  cursor: "pointer",
                }}
              >
                Faire une offre
              </button>
            </div>

            <div
              style={
                offer
                  ? { padding: "16px 18px", borderRadius: 20, background: "#F5F5F8" }
                  : { display: "none" }
              }
            >
              <div style={{ fontSize: 14, fontWeight: 600 }}>Votre offre</div>
              <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                {OFFERS.map((v, i) => (
                  <button
                    key={v}
                    type="button"
                    className="sm"
                    aria-pressed={ov === i}
                    onClick={() => {
                      setOv(i);
                      setSent(false);
                    }}
                    style={ov === i ? INK : { background: "#FFFFFF", color: "#0B0B0F" }}
                  >
                    <span className="m">{euros(v)}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className="sm"
                  onClick={() => {
                    setSent(true);
                  }}
                  style={{ background: "#1D2BFF", color: "#FFFFFF", marginLeft: "auto" }}
                >
                  Envoyer
                </button>
              </div>
              <div
                role="status"
                style={
                  sent
                    ? {
                        marginTop: 12,
                        fontSize: 13,
                        padding: "10px 12px",
                        borderRadius: 12,
                        background: "rgba(29,43,255,0.08)",
                        color: "#1420C8",
                      }
                    : { display: "none" }
                }
              >
                {sent &&
                  `Offre de ${euros(OFFERS[ov] ?? 0)} envoyée. Réponse sous 24 h, votre argent n’est bloqué que si elle est acceptée.`}
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                className="sm"
                aria-pressed={fav}
                onClick={() => {
                  setFav(!fav);
                }}
                style={fav ? { background: "rgba(224,53,43,0.1)", color: "#B1241B" } : GREY}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.3a4.3 4.3 0 0 1 7.5 2.5C19.5 15.4 12 20 12 20z"
                    style={
                      fav
                        ? { fill: "#D93026", stroke: "#D93026" }
                        : { fill: "none", stroke: "#0B0B0F" }
                    }
                    strokeWidth="2"
                    strokeLinejoin="round"
                  />
                </svg>
                {fav ? "Dans vos favoris" : "Favori"}
              </button>
              <button
                type="button"
                className="sm"
                aria-pressed={alert}
                onClick={() => {
                  setAlert(!alert);
                }}
                style={alert ? { background: "rgba(30,122,69,0.12)", color: "#155C33" } : GREY}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" />
                </svg>
                {alert ? "Alerte si le prix baisse" : "Suivre le prix"}
              </button>
              <DemoLink to="Agent" className="sm" style={GREY}>
                <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M10 3.5c.6 3.9 2.6 5.9 6.5 6.5-3.9.6-5.9 2.6-6.5 6.5-.6-3.9-2.6-5.9-6.5-6.5 3.9-.6 5.9-2.6 6.5-6.5z"
                    fill="#1D2BFF"
                  />
                </svg>
                Négocier avec l'agent IA
              </DemoLink>
            </div>

            <div
              className="box"
              style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 14 }}
            >
              <div style={{ display: "flex", gap: 12 }}>
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  style={{ flex: "none" }}
                  aria-hidden="true"
                >
                  <path
                    d="M12 2.8 4.6 5.8v6.1c0 4.6 3.1 7.8 7.4 9.3 4.3-1.5 7.4-4.7 7.4-9.3V5.8z"
                    fill="#1D2BFF"
                  />
                  <path
                    d="m8.6 12 2.4 2.4 4.6-4.8"
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>
                  <b style={{ fontWeight: 600 }}>Argent bloqué jusqu'à la remise.</b> Le vendeur est
                  payé quand vous confirmez.
                </span>
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  style={{ flex: "none" }}
                  aria-hidden="true"
                >
                  <rect x="4" y="4" width="16" height="16" rx="4" fill="#0B8F9A" />
                  <path
                    d="M8 10h8M8 14h5"
                    stroke="#FFFFFF"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                  />
                </svg>
                <span>
                  <b style={{ fontWeight: 600 }}>Passeport produit</b> : 4 propriétaires connus
                  depuis 1857, certificat AG-1857-0042.
                </span>
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  style={{ flex: "none" }}
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="9" fill="#C2540A" />
                  <path
                    d="M12 7.5v5l3 2"
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
                <span>
                  <b style={{ fontWeight: 600 }}>48 h pour vérifier.</b> Non conforme ? Médiation et
                  remboursement.
                </span>
              </div>
            </div>
          </section>
        </div>

        {/* Onglets */}
        <section style={{ marginTop: 48 }}>
          <div
            className="pd-tabs"
            style={{ display: "flex", borderBottom: "0.5px solid rgba(60,60,67,0.18)" }}
            role="tablist"
            aria-label="Détails de l’annonce"
            onKeyDown={onTabKey}
          >
            {TABS.map((label, i) => (
              <button
                key={label}
                ref={(el) => {
                  tabRefs.current[i] = el;
                }}
                type="button"
                id={`pd-tab-${String(i)}`}
                className={tab === i ? "tb on" : "tb"}
                role="tab"
                aria-selected={tab === i}
                aria-controls="pd-panel"
                tabIndex={tab === i ? 0 : -1}
                onClick={() => {
                  setTab(i);
                }}
              >
                {label}
              </button>
            ))}
          </div>

          <div id="pd-panel" role="tabpanel" aria-labelledby={`pd-tab-${String(tab)}`}>
            {tab === 0 && <DescriptionPanel />}
            {tab === 1 && <PassportPanel />}
            {tab === 2 && <PricePanel />}
          </div>
        </section>

        {/* Similaires */}
        <section style={{ marginTop: 48 }}>
          <h2
            style={{ margin: "0 0 18px", fontSize: 24, fontWeight: 700, letterSpacing: "-0.03em" }}
          >
            Vous aimerez aussi
          </h2>
          <div
            className="pd-similar"
            style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 18 }}
          >
            {SIMILAR.map((p) => (
              <DemoLink key={p.name} to={p.to} className="pc">
                <span className="im">
                  <img src={p.src} alt={p.alt} style={p.img} />
                </span>
                <span>
                  <span style={{ display: "block", fontSize: 14, color: "#3A3A3F" }}>{p.name}</span>
                  <span className="m" style={{ display: "block", fontSize: 17 }}>
                    {euros(p.price)}
                  </span>
                </span>
              </DemoLink>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function DescriptionPanel() {
  return (
    <div
      className="pd-panel"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.4fr)",
        gap: 48,
        paddingTop: 24,
      }}
    >
      <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6, color: "#3A3A3F" }}>
        Exemplaire de l'édition originale publiée par Poulet-Malassis et de Broise en juin 1857,
        avant la condamnation des six poèmes. Reliure en toile verte d'époque, dos et coins frottés,
        quelques rousseurs éparses. Ex-libris d'une collection lyonnaise. Livré dans une boîte de
        conservation sur mesure.
      </p>
      <div className="spec">
        <div>
          <span>Auteur</span>Charles Baudelaire
        </div>
        <div>
          <span>Éditeur</span>Poulet-Malassis et de Broise
        </div>
        <div>
          <span>Année</span>1857
        </div>
        <div>
          <span>Reliure</span>Toile verte d'époque
        </div>
        <div>
          <span>État</span>Bon, rousseurs éparses
        </div>
        <div>
          <span>Format</span>19 × 12 cm, 252 pages
        </div>
      </div>
    </div>
  );
}

function PassportPanel() {
  return (
    <div
      className="pd-panel"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
        gap: 48,
        paddingTop: 26,
      }}
    >
      <div>
        {PASSPORT.map(([y, t, d], i) => (
          <div key={y} className="tl">
            <span
              style={{
                position: "relative",
                zIndex: 1,
                flex: "none",
                width: 16,
                height: 16,
                borderRadius: "50%",
                marginTop: 2,
                boxSizing: "border-box",
                ...(i === PASSPORT.length - 1
                  ? { background: "#1D2BFF" }
                  : { background: "#FFFFFF", border: "2px solid #1D2BFF" }),
              }}
            />
            <div>
              <div className="m" style={{ fontSize: 13, color: "#6E6E73" }}>
                {y}
              </div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{t}</div>
              <div style={{ fontSize: 14, color: "#6E6E73", marginTop: 2 }}>{d}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="box" style={{ alignSelf: "start" }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>Ce que garantit le passeport</div>
        <div style={{ fontSize: 14, color: "#3A3A3F", marginTop: 8, lineHeight: 1.55 }}>
          Chaque vente sur TROVÉLYA s'inscrit automatiquement dans l'historique de l'objet. Une
          vente faite hors d'TROVÉLYA n'y figure pas : l'objet perd sa traçabilité et une partie de
          sa valeur de revente.
        </div>
      </div>
    </div>
  );
}

function PricePanel() {
  return (
    <div
      className="pd-panel"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 1fr)",
        gap: 48,
        paddingTop: 24,
        alignItems: "center",
      }}
    >
      <svg
        viewBox="0 0 640 220"
        style={{ width: "100%", height: 220 }}
        role="img"
        aria-label="Prix de 11 200 € en 2019 à 18 500 € en 2026"
      >
        <g stroke="rgba(60,60,67,0.1)">
          <path d="M40 30H640M40 90H640M40 150H640M40 200H640" />
        </g>
        <g style={{ fontFamily: "var(--demo-mono)" }} fontSize="11" fill="#6E6E73">
          <text x="0" y="34">
            20 k
          </text>
          <text x="0" y="94">
            16 k
          </text>
          <text x="0" y="154">
            12 k
          </text>
        </g>
        <path
          d="M60 162 L150 150 L240 136 L330 118 L420 96 L510 74 L600 54 L600 200 L60 200Z"
          fill="rgba(29,43,255,0.08)"
        />
        <path
          d="M60 162 L150 150 L240 136 L330 118 L420 96 L510 74 L600 54"
          fill="none"
          stroke="#1D2BFF"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <path
          d="M600 54 L640 42"
          fill="none"
          stroke="#1E7A45"
          strokeWidth="2.5"
          strokeDasharray="5 5"
        />
        <g fill="#1D2BFF">
          <circle cx="60" cy="162" r="4" />
          <circle cx="330" cy="118" r="4" />
          <circle cx="600" cy="54" r="5" />
        </g>
        <g style={{ fontFamily: "var(--demo-sans)" }} fontSize="11" fill="#6E6E73">
          <text x="50" y="216">
            2019
          </text>
          <text x="320" y="216">
            2022
          </text>
          <text x="585" y="216">
            2026
          </text>
        </g>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="box">
          <div style={{ fontSize: 13, color: "#6E6E73" }}>Cote TROVÉLYA aujourd'hui</div>
          <div className="m" style={{ fontSize: 24, marginTop: 4 }}>
            17 900 à 19 400 €
          </div>
        </div>
        <div className="box">
          <div style={{ fontSize: 13, color: "#6E6E73" }}>Évolution depuis 2019</div>
          <div className="m" style={{ fontSize: 24, marginTop: 4, color: "#1E7A45" }}>
            +65 %
          </div>
        </div>
      </div>
    </div>
  );
}
