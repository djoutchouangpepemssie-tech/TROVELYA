"use client";

import "./catalog.css";

import { type CSSProperties, useState } from "react";

import { IMG, type ImageKey } from "../_components/data";
import { DemoHeader } from "../_components/DemoHeader";
import { DemoLink } from "../_components/DemoLink";
import { euros, HeartIcon, VerifiedIcon } from "../_components/icons";

type Mode = "buy" | "auc" | "live";
type Item = {
  t: string;
  p: number;
  img: ImageKey;
  cat: string;
  mode: Mode;
  end?: string;
  cond: string;
  km: number;
  city: string;
  fr: boolean;
  v: boolean;
  hd: boolean;
  ad?: boolean;
  href: string;
  crop: CSSProperties;
};

// The mock-up's fictitious listings.
const D: Item[] = [
  {
    t: "Montre automatique, 1968",
    p: 1240,
    img: "watch",
    cat: "Montres",
    mode: "auc",
    end: "02:14",
    cond: "Très bon état",
    km: 1.2,
    city: "Paris 11e",
    fr: true,
    v: true,
    hd: true,
    href: "Auction",
    crop: {},
  },
  {
    t: "Lampe champignon opaline",
    p: 95,
    img: "lamp",
    cat: "Maison",
    mode: "buy",
    cond: "Très bon état",
    km: 0.8,
    city: "Paris 11e",
    fr: true,
    v: true,
    hd: true,
    ad: true,
    href: "WebProduct",
    crop: {},
  },
  {
    t: "Les Fleurs du mal, 1857",
    p: 18500,
    img: "book",
    cat: "Livres",
    mode: "buy",
    cond: "Bon état",
    km: 392,
    city: "Lyon 5e",
    fr: true,
    v: true,
    hd: true,
    href: "WebProduct",
    crop: {},
  },
  {
    t: "Vinyle jazz, pressage original",
    p: 120,
    img: "vinyl",
    cat: "Musique",
    mode: "buy",
    cond: "Bon état",
    km: 4.6,
    city: "Paris 18e",
    fr: true,
    v: false,
    hd: true,
    href: "WebProduct",
    crop: { transform: "scale(1.5)", objectPosition: "40% 55%", filter: "sepia(0.35)" },
  },
  {
    t: "Objectif 50 mm f/1.4",
    p: 420,
    img: "lens",
    cat: "Photo",
    mode: "auc",
    end: "08:41",
    cond: "Très bon état",
    km: 4.1,
    city: "Montreuil",
    fr: true,
    v: false,
    hd: true,
    href: "Auction",
    crop: {},
  },
  {
    t: "Vase en grès émaillé",
    p: 64,
    img: "vase",
    cat: "Céramique",
    mode: "buy",
    cond: "Neuf",
    km: 2.4,
    city: "Paris 20e",
    fr: true,
    v: false,
    hd: true,
    href: "WebProduct",
    crop: {},
  },
  {
    t: "Les Fleurs du mal, réédition 1868",
    p: 240,
    img: "book",
    cat: "Livres",
    mode: "auc",
    end: "1 h 20",
    cond: "Bon état",
    km: 17,
    city: "Versailles",
    fr: true,
    v: true,
    hd: true,
    href: "Auction",
    crop: { filter: "hue-rotate(-115deg) saturate(1.2)", transform: "scale(1.2)" },
  },
  {
    t: "Lot de vinyles soul, 1972",
    p: 46,
    img: "vinyl",
    cat: "Musique",
    mode: "live",
    cond: "Bon état",
    km: 392,
    city: "Lyon",
    fr: true,
    v: true,
    hd: false,
    href: "WebLive",
    crop: {},
  },
  {
    t: "Vase céladon",
    p: 88,
    img: "vase",
    cat: "Céramique",
    mode: "live",
    cond: "Très bon état",
    km: 498,
    city: "Bordeaux",
    fr: true,
    v: false,
    hd: false,
    href: "WebLive",
    crop: { filter: "hue-rotate(-40deg) saturate(0.7) brightness(1.12)" },
  },
  {
    t: "Montre de plongée, 1974",
    p: 860,
    img: "watch",
    cat: "Montres",
    mode: "buy",
    cond: "Très bon état",
    km: 264,
    city: "Bruxelles · Belgique",
    fr: false,
    v: true,
    hd: false,
    href: "WebProduct",
    crop: { filter: "hue-rotate(150deg) saturate(0.9)", transform: "scale(1.3)" },
  },
  {
    t: "Lampe d’atelier en laiton",
    p: 180,
    img: "lamp",
    cat: "Maison",
    mode: "buy",
    cond: "Bon état",
    km: 640,
    city: "Milan · Italie",
    fr: false,
    v: true,
    hd: false,
    href: "WebProduct",
    crop: { filter: "sepia(0.7) saturate(1.4)", transform: "scale(1.25)" },
  },
  {
    t: "Objectif 85 mm f/1.8",
    p: 310,
    img: "lens",
    cat: "Photo",
    mode: "buy",
    cond: "Neuf",
    km: 878,
    city: "Berlin · Allemagne",
    fr: false,
    v: true,
    hd: false,
    href: "WebProduct",
    crop: { transform: "scale(1.35)", filter: "hue-rotate(40deg)" },
  },
];

const DIST: [string, (x: Item) => boolean, string][] = [
  ["5 km", (x) => x.km <= 5, "à moins de 5 km de Paris 11e"],
  ["Paris et alentours", (x) => x.km <= 20, "Paris et alentours"],
  ["France", (x) => x.fr, "toute la France"],
  ["Toute l’UE", () => true, "toute l’Union européenne"],
];
const PR: [string, (x: Item) => boolean][] = [
  ["Tous les prix", () => true],
  ["Moins de 100 €", (x) => x.p < 100],
  ["100 à 1 000 €", (x) => x.p >= 100 && x.p <= 1000],
  ["Plus de 1 000 €", (x) => x.p > 1000],
];
const CATS = ["Montres", "Musique", "Livres", "Maison", "Photo", "Céramique"];
const MODES: [Mode, string][] = [
  ["buy", "Achat immédiat"],
  ["auc", "Enchère"],
  ["live", "En live"],
];
const CONDS = ["Neuf", "Très bon état", "Bon état"];
const SORTS = ["Pertinence", "Plus proches", "Prix croissant", "Prix décroissant"];

type Flags = Record<string, boolean>;
type Filters = {
  dist: number;
  cats: Flags;
  modes: Flags;
  price: number;
  conds: Flags;
  ver: boolean;
  hand: boolean;
  sort: number;
};
type Skip = "dist" | "price" | "cat" | "mode" | "cond";

const INITIAL: Filters = {
  dist: 1,
  cats: {},
  modes: {},
  price: 0,
  conds: {},
  ver: false,
  hand: false,
  sort: 0,
};

const ON: CSSProperties = { background: "#0B0B0F", color: "#FFFFFF" };
const OFF: CSSProperties = { background: "#F2F2F7", color: "#1C1C22" };

const anyOn = (o: Flags) => Object.values(o).some(Boolean);

/** Badge colours in the catalogue (the "buy" badge is a touch more opaque than elsewhere). */
function badgeColours(mode: Mode): CSSProperties {
  if (mode === "live") return { background: "#D93026", color: "#FFFFFF" };
  if (mode === "auc") return { background: "rgba(11,11,15,0.78)", color: "#FFFFFF" };
  return { background: "rgba(255,255,255,0.92)", color: "#0B0B0F" };
}

function badgeLabel(x: Item): string {
  if (x.mode === "live") return "En live";
  if (x.mode === "auc") return `Enchère · ${x.end ?? ""}`;
  return "Achat immédiat";
}

function CheckRow({
  label,
  count,
  on,
  onToggle,
}: {
  label: string;
  count: number;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <button type="button" className="ck" role="checkbox" aria-checked={on} onClick={onToggle}>
      <span
        className="bx"
        style={on ? { background: "#1D2BFF" } : { boxShadow: "inset 0 0 0 1.5px #C7C7CC" }}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          style={on ? undefined : { display: "none" }}
          aria-hidden="true"
        >
          <path
            d="m5 12.5 4.5 4.5L19 7.5"
            fill="none"
            stroke="#FFFFFF"
            strokeWidth="3.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {label}
      <span className="ct">{count}</span>
    </button>
  );
}

function SwitchRow({
  title,
  hint,
  on,
  onToggle,
}: {
  title: string;
  hint: string;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
        <div style={{ fontSize: 12, color: "#6E6E73" }}>{hint}</div>
      </div>
      <button
        type="button"
        className="sw"
        role="switch"
        aria-checked={on}
        aria-label={title}
        onClick={onToggle}
        style={{ background: on ? "#1D2BFF" : "rgba(118,118,128,0.3)" }}
      >
        <span style={{ left: on ? 20 : 2 }} />
      </button>
    </div>
  );
}

/** Mock-up screen WebCatalog: filters, sort, grid or list, favourites and saved search. */
export function Catalog() {
  const [f, setF] = useState<Filters>(INITIAL);
  const [view, setView] = useState(0);
  const [saved, setSaved] = useState(false);
  const [fav, setFav] = useState<Record<number, boolean>>({});

  const set = (patch: Partial<Filters>) => {
    setF((prev) => ({ ...prev, ...patch }));
  };
  // The mock-up's reset keeps favourites and the view, and clears the saved search.
  const reset = () => {
    setF(INITIAL);
    setSaved(false);
  };

  const pass = (x: Item, skip?: Skip) =>
    (skip === "dist" || (DIST[f.dist]?.[1](x) ?? true)) &&
    (skip === "price" || (PR[f.price]?.[1](x) ?? true)) &&
    (skip === "cat" || !anyOn(f.cats) || f.cats[x.cat] === true) &&
    (skip === "mode" || !anyOn(f.modes) || f.modes[x.mode] === true) &&
    (skip === "cond" || !anyOn(f.conds) || f.conds[x.cond] === true) &&
    (!f.ver || x.v) &&
    (!f.hand || x.hd);

  const active: { n: string; rm: () => void }[] = [
    {
      n: DIST[f.dist]?.[0] ?? "",
      rm: () => {
        set({ dist: 3 });
      },
    },
  ];
  if (f.price)
    active.push({
      n: PR[f.price]?.[0] ?? "",
      rm: () => {
        set({ price: 0 });
      },
    });
  for (const c of CATS) {
    if (f.cats[c])
      active.push({
        n: c,
        rm: () => {
          set({ cats: { ...f.cats, [c]: false } });
        },
      });
  }
  for (const [k, n] of MODES) {
    if (f.modes[k])
      active.push({
        n,
        rm: () => {
          set({ modes: { ...f.modes, [k]: false } });
        },
      });
  }
  for (const c of CONDS) {
    if (f.conds[c])
      active.push({
        n: c,
        rm: () => {
          set({ conds: { ...f.conds, [c]: false } });
        },
      });
  }
  if (f.ver)
    active.push({
      n: "Vendeurs vérifiés",
      rm: () => {
        set({ ver: false });
      },
    });
  if (f.hand)
    active.push({
      n: "Remise en main propre",
      rm: () => {
        set({ hand: false });
      },
    });
  const chips = f.dist === 3 && active.length === 1 ? [] : active;

  const results = D.map((x, i) => ({ ...x, i })).filter((x) => pass(x));
  if (f.sort === 1) results.sort((a, b) => a.km - b.km);
  if (f.sort === 2) results.sort((a, b) => a.p - b.p);
  if (f.sort === 3) results.sort((a, b) => b.p - a.p);

  const list = view === 1;
  const empty = results.length === 0;

  const gridStyle: CSSProperties = empty
    ? { display: "none" }
    : list
      ? { display: "flex", flexDirection: "column", gap: 12, marginTop: 18 }
      : {
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
          gap: "26px 18px",
          marginTop: 18,
        };

  return (
    <div
      className="demo-catalog"
      style={{
        width: "100%",
        minHeight: 1200,
        background: "#FFFFFF",
        color: "#0B0B0F",
        position: "relative",
      }}
    >
      <DemoHeader active="Collection" />

      <div
        className="wrap catalog-layout"
        style={{
          display: "flex",
          gap: 36,
          paddingTop: 22,
          paddingBottom: 56,
          alignItems: "flex-start",
        }}
      >
        {/* Filtres */}
        <aside
          className="catalog-filters"
          style={{ flex: "none", width: 272 }}
          aria-label="Filtres"
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              paddingBottom: 14,
            }}
          >
            <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.03em" }}>Filtres</span>
            <button
              type="button"
              onClick={reset}
              style={{
                border: 0,
                background: "none",
                font: "600 14px var(--demo-sans)",
                color: "#1D2BFF",
                cursor: "pointer",
              }}
            >
              Tout effacer
            </button>
          </div>

          <div className="fs">
            <div className="fh">Distance</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              {DIST.map(([n], i) => (
                <button
                  key={n}
                  type="button"
                  className="chip"
                  aria-pressed={f.dist === i}
                  onClick={() => {
                    set({ dist: i });
                  }}
                  style={f.dist === i ? ON : OFF}
                >
                  {n}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 12, color: "#6E6E73", marginTop: 10, lineHeight: 1.4 }}>
              Les objets les plus proches passent en premier : c&apos;est la priorité territoriale.
            </div>
          </div>

          <div className="fs">
            <div className="fh">Catégorie</div>
            {CATS.map((c) => (
              <CheckRow
                key={c}
                label={c}
                count={D.filter((x) => x.cat === c && pass(x, "cat")).length}
                on={f.cats[c] === true}
                onToggle={() => {
                  set({ cats: { ...f.cats, [c]: !f.cats[c] } });
                }}
              />
            ))}
          </div>

          <div className="fs">
            <div className="fh">Mode de vente</div>
            {MODES.map(([k, n]) => (
              <CheckRow
                key={k}
                label={n}
                count={D.filter((x) => x.mode === k && pass(x, "mode")).length}
                on={f.modes[k] === true}
                onToggle={() => {
                  set({ modes: { ...f.modes, [k]: !f.modes[k] } });
                }}
              />
            ))}
          </div>

          <div className="fs">
            <div className="fh">Prix</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {PR.map(([n], i) => (
                <button
                  key={n}
                  type="button"
                  className="chip"
                  aria-pressed={f.price === i}
                  onClick={() => {
                    set({ price: i });
                  }}
                  style={f.price === i ? ON : OFF}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <div className="fs">
            <div className="fh">État</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {CONDS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className="chip"
                  aria-pressed={f.conds[c] === true}
                  onClick={() => {
                    set({ conds: { ...f.conds, [c]: !f.conds[c] } });
                  }}
                  style={f.conds[c] ? ON : OFF}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          <div className="fs" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <SwitchRow
              title="Vendeurs vérifiés"
              hint="identité et objets contrôlés"
              on={f.ver}
              onToggle={() => {
                set({ ver: !f.ver });
              }}
            />
            <SwitchRow
              title="Remise en main propre"
              hint="paiement protégé, code au rendez-vous"
              on={f.hand}
              onToggle={() => {
                set({ hand: !f.hand });
              }}
            />
          </div>
        </aside>

        {/* Résultats */}
        <main style={{ flex: 1, minWidth: 0 }}>
          <nav aria-label="Fil d’Ariane" style={{ fontSize: 13, color: "#6E6E73" }}>
            <DemoLink to="WebHome" style={{ color: "#6E6E73" }}>
              Accueil
            </DemoLink>{" "}
            ›{" "}
            <DemoLink to="WebHome" style={{ color: "#6E6E73" }}>
              Collection
            </DemoLink>{" "}
            › <span style={{ color: "#0B0B0F" }}>Vintage</span>
          </nav>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-end",
              gap: 16,
              marginTop: 8,
              flexWrap: "wrap",
            }}
          >
            <div>
              <h1 style={{ margin: 0, fontSize: 32, fontWeight: 700, letterSpacing: "-0.04em" }}>
                Objets vintage et de collection
              </h1>
              <div style={{ fontSize: 15, color: "#6E6E73", marginTop: 4 }} aria-live="polite">
                <b className="m" style={{ color: "#0B0B0F" }}>
                  {results.length}
                </b>{" "}
                résultats · {DIST[f.dist]?.[2]}
              </div>
            </div>
            <button
              type="button"
              aria-pressed={saved}
              onClick={() => {
                setSaved(!saved);
              }}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                height: 40,
                padding: "0 16px",
                borderRadius: 999,
                border: 0,
                cursor: "pointer",
                font: "600 14px var(--demo-sans)",
                ...(saved
                  ? { background: "rgba(30,122,69,0.12)", color: "#155C33" }
                  : { background: "#EEF0FF", color: "#1420C8" }),
              }}
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
                <path d="M10 20.5a2 2 0 0 0 4 0" />
              </svg>
              {saved ? "Alerte activée" : "Enregistrer la recherche"}
            </button>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 12,
              marginTop: 18,
              flexWrap: "wrap",
            }}
          >
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", minHeight: 32 }}>
              {chips.map((a) => (
                <button
                  key={a.n}
                  type="button"
                  className="ac"
                  onClick={a.rm}
                  aria-label={`Retirer le filtre ${a.n}`}
                >
                  {a.n}
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    aria-hidden="true"
                  >
                    <path d="m7 7 10 10M17 7 7 17" />
                  </svg>
                </button>
              ))}
            </div>
            <div
              className="catalog-tools"
              style={{ display: "flex", gap: 10, alignItems: "center" }}
            >
              <div className="seg" role="group" aria-label="Trier">
                {SORTS.map((n, i) => (
                  <button
                    key={n}
                    type="button"
                    className={f.sort === i ? "sg on" : "sg"}
                    aria-pressed={f.sort === i}
                    onClick={() => {
                      set({ sort: i });
                    }}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <div className="seg" role="group" aria-label="Affichage">
                <button
                  type="button"
                  className={view === 0 ? "sg on" : "sg"}
                  aria-pressed={view === 0}
                  onClick={() => {
                    setView(0);
                  }}
                  aria-label="Grille"
                  style={{ width: 38, padding: 0, display: "grid", placeItems: "center" }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <rect x="4" y="4" width="7" height="7" rx="1.6" />
                    <rect x="13" y="4" width="7" height="7" rx="1.6" />
                    <rect x="4" y="13" width="7" height="7" rx="1.6" />
                    <rect x="13" y="13" width="7" height="7" rx="1.6" />
                  </svg>
                </button>
                <button
                  type="button"
                  className={view === 1 ? "sg on" : "sg"}
                  aria-pressed={view === 1}
                  onClick={() => {
                    setView(1);
                  }}
                  aria-label="Liste"
                  style={{ width: 38, padding: 0, display: "grid", placeItems: "center" }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <rect x="4" y="5" width="16" height="3.4" rx="1.4" />
                    <rect x="4" y="10.3" width="16" height="3.4" rx="1.4" />
                    <rect x="4" y="15.6" width="16" height="3.4" rx="1.4" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          {empty && (
            <div
              style={{
                marginTop: 40,
                padding: 48,
                borderRadius: 24,
                background: "#F5F5F8",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: 20, fontWeight: 600 }}>Aucun objet avec ces filtres</div>
              <div style={{ fontSize: 15, color: "#6E6E73", marginTop: 6 }}>
                Élargissez la distance ou publiez une demande : les vendeurs viendront à vous.
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  justifyContent: "center",
                  marginTop: 18,
                  flexWrap: "wrap",
                }}
              >
                <button type="button" className="btnp" onClick={reset}>
                  Effacer les filtres
                </button>
                <DemoLink to="Request" className="btnp" style={{ background: "#0B0B0F" }}>
                  Publier une demande
                </DemoLink>
              </div>
            </div>
          )}

          <div className={list ? "catalog-list" : "catalog-grid"} style={gridStyle}>
            {results.map((x) => {
              const on = fav[x.i] === true;
              return (
                // The favourite button sits beside the link, not inside it (no nested controls).
                <div key={x.i} style={{ position: "relative", minWidth: 0 }}>
                  <DemoLink
                    to={x.href}
                    className="pc"
                    style={
                      list
                        ? {
                            flexDirection: "row",
                            gap: 18,
                            alignItems: "center",
                            padding: 12,
                            borderRadius: 20,
                            boxShadow: "inset 0 0 0 0.5px rgba(60,60,67,0.16)",
                          }
                        : { flexDirection: "column", gap: 9 }
                    }
                  >
                    <span
                      className="im"
                      style={list ? { width: 132, height: 132 } : { aspectRatio: "1 / 1" }}
                    >
                      <img src={IMG[x.img]} alt={x.t} style={x.crop} />
                      <span
                        className="bdg"
                        style={{
                          ...badgeColours(x.mode),
                          ...(list
                            ? { top: "auto", bottom: 8, left: 8, fontSize: 11, padding: "4px 8px" }
                            : {}),
                        }}
                      >
                        {badgeLabel(x)}
                      </span>
                    </span>
                    <span
                      style={list ? { flex: 1, minWidth: 0 } : { display: "block", minWidth: 0 }}
                    >
                      {x.ad && (
                        <span
                          style={{
                            display: "block",
                            fontSize: 11,
                            fontWeight: 600,
                            color: "#6E6E73",
                            letterSpacing: "0.02em",
                            marginBottom: 2,
                          }}
                        >
                          Sponsorisé
                        </span>
                      )}
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
                        {x.t}
                      </span>
                      <span className="m" style={{ display: "block", fontSize: 17, marginTop: 2 }}>
                        {euros(x.p)}
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
                        {x.city + (x.km < 100 ? ` · ${String(x.km).replace(".", ",")} km` : "")}
                        <VerifiedIcon hidden={!x.v} />
                      </span>
                      {list && (
                        <span
                          style={{ display: "block", fontSize: 13, color: "#3A3A3F", marginTop: 8 }}
                        >
                          {x.cond} · {x.hd ? "remise en main propre possible" : "livraison suivie"}
                        </span>
                      )}
                    </span>
                  </DemoLink>
                  <button
                    type="button"
                    className="fav"
                    aria-label={`Ajouter aux favoris : ${x.t}`}
                    aria-pressed={on}
                    onClick={() => {
                      setFav((prev) => ({ ...prev, [x.i]: !on }));
                    }}
                    style={
                      list ? { left: 100, right: "auto", top: "50%", marginTop: -56 } : undefined
                    }
                  >
                    <HeartIcon on={on} />
                  </button>
                </div>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}
