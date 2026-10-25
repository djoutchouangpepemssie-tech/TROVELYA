"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IMG, type ImageKey } from "./data";
import { DemoLink } from "./DemoLink";

type Category = { n: string; img: ImageKey; title: string; cols: [string, string[]][] };

// The mock-up's categories and their mega-menu (WebHome).
const CATS: Category[] = [
  {
    n: "Mode",
    img: "vase",
    title: "Créateurs européens",
    cols: [
      ["Femme", ["Robes", "Manteaux", "Sacs", "Chaussures", "Bijoux"]],
      ["Homme", ["Vestes", "Sneakers", "Montres", "Accessoires"]],
      ["Enfant", ["0 à 2 ans", "3 à 8 ans", "Ados"]],
      ["Seconde main", ["Vintage", "Luxe vérifié", "Lots"]],
    ],
  },
  {
    n: "Maison",
    img: "lamp",
    title: "Luminaires d’atelier",
    cols: [
      ["Décoration", ["Luminaires", "Céramique", "Miroirs", "Art mural"]],
      ["Mobilier", ["Assises", "Tables", "Rangements"]],
      ["Cuisine", ["Vaisselle", "Électroménager", "Arts de la table"]],
      ["Jardin", ["Mobilier extérieur", "Plantes", "Outils"]],
    ],
  },
  {
    n: "High-tech",
    img: "lens",
    title: "Optiques reconditionnées",
    cols: [
      ["Photo", ["Objectifs", "Boîtiers", "Argentique", "Éclairage"]],
      ["Son", ["Platines", "Enceintes", "Casques"]],
      ["Informatique", ["Portables", "Tablettes", "Écrans"]],
      ["Jeux vidéo", ["Consoles", "Rétro", "Jeux"]],
    ],
  },
  {
    n: "Collection",
    img: "vinyl",
    title: "Vinyles originaux",
    cols: [
      ["Musique", ["Vinyles", "Platines vintage", "Affiches"]],
      ["Objets d’art", ["Céramique", "Tableaux", "Sculptures"]],
      ["Cartes et monnaies", ["Cartes à collectionner", "Pièces", "Timbres"]],
      ["Jouets", ["Figurines", "Modélisme", "LEGO"]],
    ],
  },
  {
    n: "Livres",
    img: "book",
    title: "Éditions originales",
    cols: [
      ["Livres rares", ["Éditions originales", "Dédicacés", "Reliures"]],
      ["Littérature", ["Romans", "Poésie", "Fantasy"]],
      ["Bande dessinée", ["Albums", "Mangas", "Planches"]],
      ["Jeunesse", ["Albums", "Premières lectures"]],
    ],
  },
  {
    n: "Montres et bijoux",
    img: "watch",
    title: "Montres de 1950 à 1980",
    cols: [
      ["Montres", ["Automatiques", "Vintage", "Chronographes", "Luxe vérifié"]],
      ["Bijoux", ["Bagues", "Colliers", "Boucles d’oreilles"]],
      ["Entretien", ["Bracelets", "Écrins", "Réparation"]],
      ["Expertise", ["Certificats", "Estimation IA"]],
    ],
  },
  {
    n: "Sport",
    img: "lens",
    title: "Vélos de route",
    cols: [
      ["Cycle", ["Vélos", "Pièces", "Équipement"]],
      ["Glisse", ["Ski", "Surf", "Snowboard"]],
      ["Fitness", ["Matériel", "Textile"]],
      ["Plein air", ["Randonnée", "Camping"]],
    ],
  },
  {
    n: "Véhicules",
    img: "watch",
    title: "Classiques européennes",
    cols: [
      ["Auto", ["Voitures", "Pièces", "Accessoires"]],
      ["Deux-roues", ["Motos", "Scooters", "Vélos électriques"]],
      ["Loisirs", ["Camping-cars", "Bateaux"]],
      ["Équipement", ["Casques", "Blousons"]],
    ],
  },
  {
    n: "Enfants",
    img: "vase",
    title: "Jouets en bois",
    cols: [
      ["Puériculture", ["Poussettes", "Sièges auto", "Lits"]],
      ["Jouets", ["Éveil", "Jeux de société", "Peluches"]],
      ["Vêtements", ["Bébé", "Enfant"]],
      ["École", ["Cartables", "Livres"]],
    ],
  },
];

type Props = {
  /** Home: the categories open the mega-menu. Elsewhere they lead back home. */
  mega?: boolean;
  /** Category underlined on catalogue and product pages. */
  active?: string;
};

/** The mock-up's site header (WebHome, WebCatalog, WebProduct, WebLive). */
export function DemoHeader({ mega = false, active }: Props) {
  const [menu, setMenu] = useState(-1);
  const current = menu >= 0 ? CATS[menu] : undefined;

  // Escape closes the mega-menu.
  useEffect(() => {
    if (menu < 0) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenu(-1);
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  return (
    <>
      <header
        style={{
          position: "relative",
          zIndex: 5,
          background: "#FFFFFF",
          borderBottom: "0.5px solid rgba(60,60,67,0.16)",
        }}
      >
        <div
          className="wrap demo-header-row"
          style={{ display: "flex", alignItems: "center", gap: 18, height: 76 }}
        >
          <Link
            href="/fr/demo"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              color: "#0B0B0F",
              flex: "none",
            }}
          >
            <span
              style={{
                width: 36,
                height: 36,
                borderRadius: 11,
                background: "linear-gradient(155deg, #5866FF, #1420C8)",
                display: "grid",
                placeItems: "center",
                boxShadow: "0 6px 14px -6px rgba(29,43,255,0.7)",
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4.5 4h15v3.8h-5.6V20.5h-3.8V7.8H4.5z" fill="#FFFFFF" />
              </svg>
            </span>
            <span style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.045em" }}>
              TROVÉLYA
            </span>
          </Link>
          <DemoLink
            to="Search"
            className="demo-hide-narrow"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              height: 40,
              padding: "0 12px",
              borderRadius: 999,
              color: "#1C1C22",
              fontSize: 13,
              fontWeight: 500,
              boxShadow: "inset 0 0 0 0.5px rgba(60,60,67,0.25)",
              flex: "none",
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 21s-6.6-5.5-6.6-11a6.6 6.6 0 0 1 13.2 0c0 5.5-6.6 11-6.6 11z"
                fill="#1D2BFF"
              />
              <circle cx="12" cy="10" r="2.4" fill="#FFFFFF" />
            </svg>
            Paris 11e · 5 km
          </DemoLink>
          <form
            role="search"
            className="demo-header-search"
            onSubmit={(event) => {
              event.preventDefault();
              window.location.assign("/fr/demo/catalogue");
            }}
            style={{
              flex: 1,
              minWidth: 260,
              display: "flex",
              alignItems: "center",
              gap: 10,
              height: 48,
              padding: "0 6px 0 18px",
              borderRadius: 999,
              background: "#F2F2F7",
              margin: 0,
            }}
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#6E6E73"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="6.5" />
              <path d="m20 20-4.2-4.2" />
            </svg>
            <label htmlFor="hq" className="sr-only">
              Rechercher sur TROVÉLYA
            </label>
            <input
              id="hq"
              placeholder="Rechercher un objet, une marque, un vendeur…"
              style={{
                flex: 1,
                minWidth: 0,
                border: 0,
                background: "transparent",
                font: "16px var(--demo-sans)",
                color: "#0B0B0F",
                outlineOffset: 4,
              }}
            />
            <DemoLink
              to="VisualSearch"
              aria-label="Rechercher avec une photo"
              style={{
                width: 36,
                height: 36,
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                color: "#1C1C22",
              }}
            >
              <svg
                width="19"
                height="19"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M4 8.5h3.2l1.8-2.5h6l1.8 2.5H20V19H4z" />
                <circle cx="12" cy="13" r="3.2" />
              </svg>
            </DemoLink>
            <button type="submit" className="btnp" style={{ height: 38, padding: "0 16px" }}>
              Rechercher
            </button>
          </form>
          <nav
            aria-label="Raccourcis"
            className="demo-hide-narrow"
            style={{ display: "flex", alignItems: "center", gap: 2, flex: "none" }}
          >
            <DemoLink to="WebLive" className="hi" aria-label="Lives en cours">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none" />
                <path d="M8.2 8.2a5.4 5.4 0 0 0 0 7.6M15.8 8.2a5.4 5.4 0 0 1 0 7.6M5.3 5.3a9.5 9.5 0 0 0 0 13.4M18.7 5.3a9.5 9.5 0 0 1 0 13.4" />
              </svg>
              <span className="d" />
            </DemoLink>
            <DemoLink to="Wealth" className="hi" aria-label="Favoris">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.3a4.3 4.3 0 0 1 7.5 2.5C19.5 15.4 12 20 12 20z" />
              </svg>
            </DemoLink>
            <DemoLink to="Messages" className="hi" aria-label="Messages">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M4 5.5h16v11H9.5L4 20.5z" />
              </svg>
              <span className="d" />
            </DemoLink>
            <DemoLink to="Notifications" className="hi" aria-label="Notifications">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" />
                <path d="M10 20.5a2 2 0 0 0 4 0" />
              </svg>
            </DemoLink>
          </nav>
          <DemoLink to="WebStudio" className="btnp" style={{ flex: "none" }}>
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            Vendre
          </DemoLink>
          <DemoLink
            to="Profile"
            aria-label="Mon profil"
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: "#0B0B0F",
              color: "#FFFFFF",
              display: "grid",
              placeItems: "center",
              fontSize: 15,
              fontWeight: 600,
              flex: "none",
            }}
          >
            A
          </DemoLink>
        </div>
        <div
          className="wrap"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            overflowX: "auto",
          }}
        >
          <div style={{ display: "flex" }}>
            {CATS.map((c, i) =>
              mega ? (
                <button
                  key={c.n}
                  type="button"
                  className={menu === i ? "cat on" : "cat"}
                  aria-expanded={menu === i}
                  onClick={() => {
                    setMenu(menu === i ? -1 : i);
                  }}
                >
                  {c.n}
                </button>
              ) : (
                <Link
                  key={c.n}
                  href="/fr/demo"
                  className={active === c.n ? "cat on" : "cat"}
                  style={{ display: "grid", placeItems: "center" }}
                >
                  {c.n}
                </Link>
              ),
            )}
          </div>
          <div
            style={{
              display: "flex",
              gap: 18,
              fontSize: 14,
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            <DemoLink to="WebLive" style={{ color: "#D93026" }}>
              ● Lives
            </DemoLink>
            <DemoLink to="Auction">Enchères</DemoLink>
            <DemoLink to="Drop">Drops</DemoLink>
            <DemoLink to="Market">Bourse des objets</DemoLink>
          </div>
        </div>

        {mega && current && (
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: "100%",
              background: "#FFFFFF",
              borderTop: "0.5px solid rgba(60,60,67,0.16)",
              boxShadow: "0 24px 40px -12px rgba(0,0,0,0.18)",
            }}
          >
            <div
              className="wrap"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, minmax(0, 1fr)) 1.4fr",
                gap: 28,
                paddingTop: 26,
                paddingBottom: 30,
              }}
            >
              {current.cols.map(([heading, items]) => (
                <div key={heading} className="mega">
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0B0B0F", marginBottom: 8 }}>
                    {heading}
                  </div>
                  {items.map((item) => (
                    <Link key={item} href="/fr/demo/catalogue">
                      {item}
                    </Link>
                  ))}
                </div>
              ))}
              <Link
                href="/fr/demo/catalogue"
                style={{
                  position: "relative",
                  borderRadius: 20,
                  overflow: "hidden",
                  display: "block",
                  minHeight: 220,
                  color: "#FFFFFF",
                }}
              >
                <img
                  src={IMG[current.img]}
                  alt=""
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
                    background: "linear-gradient(180deg, rgba(0,0,0,0) 40%, rgba(0,0,0,0.55))",
                  }}
                />
                <span style={{ position: "absolute", left: 18, right: 18, bottom: 16 }}>
                  <span style={{ display: "block", fontSize: 12, fontWeight: 600, opacity: 0.85 }}>
                    Sélection de la semaine
                  </span>
                  <span
                    style={{
                      display: "block",
                      fontSize: 20,
                      fontWeight: 600,
                      letterSpacing: "-0.02em",
                      marginTop: 2,
                    }}
                  >
                    {current.title}
                  </span>
                </span>
              </Link>
            </div>
          </div>
        )}
      </header>
      {mega && menu >= 0 && (
        <div
          aria-hidden="true"
          onClick={() => {
            setMenu(-1);
          }}
          style={{ position: "fixed", inset: 0, zIndex: 4, background: "rgba(0,0,0,0.18)" }}
        />
      )}
    </>
  );
}
