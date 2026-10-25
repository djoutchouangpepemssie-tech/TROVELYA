"use client";

import "./live.css";

import { type CSSProperties, useRef, useState } from "react";

import { IMG } from "../_components/data";
import { DemoHeader } from "../_components/DemoHeader";
import { euros } from "../_components/icons";

type Kind = "u" | "s" | "b" | "me" | "sys";
type Message = { id: number; k: Kind; n: string; t: string };

const FIRST_MESSAGES: Message[] = [
  { id: 0, k: "u", n: "hanna.s", t: "Le pressage est bien d’origine ?" },
  {
    id: 1,
    k: "s",
    n: "Le Grenier de Lyon",
    t: "Oui, étiquette de 1972, vidéo de vérification dans la fiche.",
  },
  { id: 2, k: "b", n: "marco.b", t: "a enchéri 42 €" },
  {
    id: 3,
    k: "sys",
    n: "TROVÉLYA",
    t: "Un message contenant des coordonnées a été masqué. Payez uniquement dans TROVÉLYA : vous êtes protégé.",
  },
  { id: 4, k: "u", n: "julie.b", t: "Super son sur l’extrait !" },
  { id: 5, k: "b", n: "hanna.s", t: "a enchéri 46 €" },
];

// Contact details the chat masks (phone numbers, payment apps, e-mail, IBAN).
const RISKY = /\d(?:[\s.-]?\d){7,}|whats?app|lydia|paypal|telegram|@|z[ée]ro\s?(six|sept)|iban/i;
const MASK =
  /\d(?:[\s.-]?\d){7,}|whats?app|lydia|paypal|telegram|\S+@\S+|z[ée]ro\s?(six|sept)\S*|iban\S*/gi;

const AVATAR: Record<Kind, string> = {
  u: "#6E6E73",
  s: "#0B0B0F",
  b: "#C2540A",
  me: "#1D2BFF",
  sys: "#1E7A45",
};
const NAME_COLOR: Partial<Record<Kind, string>> = { me: "#1D2BFF", b: "#B34D09", sys: "#155C33" };
const WRAP: Partial<Record<Kind, CSSProperties>> = {
  sys: { padding: "10px 12px", borderRadius: 14, background: "rgba(30,122,69,0.1)" },
  me: { padding: "8px 10px", borderRadius: 14, background: "rgba(29,43,255,0.08)" },
};

const NEXT: { t: string; p: number; when: string; crop: CSSProperties }[] = [
  {
    t: "Lot de 5 albums funk, 1975",
    p: 30,
    when: "dans 2 min",
    crop: { transform: "scale(1.4)", objectPosition: "30% 50%", filter: "hue-rotate(160deg)" },
  },
  {
    t: "Jazz modal, pressage japonais",
    p: 60,
    when: "dans 6 min",
    crop: { filter: "grayscale(0.6) contrast(1.1)" },
  },
  {
    t: "Bande originale de film, 1971",
    p: 25,
    when: "dans 9 min",
    crop: {
      transform: "scale(1.6)",
      objectPosition: "60% 50%",
      filter: "hue-rotate(60deg) saturate(1.2)",
    },
  },
  {
    t: "Disco 12 pouces, édition club",
    p: 18,
    when: "dans 13 min",
    crop: { filter: "hue-rotate(250deg) saturate(1.3)" },
  },
  {
    t: "Coffret soul, 3 disques",
    p: 90,
    when: "dans 17 min",
    crop: { transform: "scale(1.25)", filter: "sepia(0.5)" },
  },
];

/** Mock-up WebLive: the stage with its bid bar, the next lots and the protected chat. */
export function Live() {
  const [price, setPrice] = useState(46);
  const [mine, setMine] = useState(false);
  const [follow, setFollow] = useState(false);
  const [muted, setMuted] = useState(false);
  const [draft, setDraft] = useState("");
  const [remind, setRemind] = useState<Record<number, boolean>>({});
  const [msgs, setMsgs] = useState(FIRST_MESSAGES);
  const nextId = useRef(FIRST_MESSAGES.length);

  // The chat keeps the last nine messages.
  const post = (list: Message[], ...added: Omit<Message, "id">[]) =>
    list.concat(added.map((m) => ({ ...m, id: nextId.current++ }))).slice(-9);

  const bidBy = (inc: number) => () => {
    const v = price + inc;
    setPrice(v);
    setMine(true);
    setMsgs(post(msgs, { k: "me", n: "Vous", t: "avez enchéri " + euros(v) }));
  };

  const send = () => {
    const t = draft.trim();
    if (!t) return;
    if (RISKY.test(t)) {
      setMsgs(
        post(
          msgs,
          { k: "me", n: "Vous", t: t.replace(MASK, "•••") },
          {
            k: "sys",
            n: "TROVÉLYA",
            t: "Coordonnées masquées. Hors d’TROVÉLYA, votre achat n’est plus protégé.",
          },
        ),
      );
    } else {
      setMsgs(post(msgs, { k: "me", n: "Vous", t }));
    }
    setDraft("");
  };

  return (
    <div
      className="demo-live"
      style={{
        width: "100%",
        minHeight: 1000,
        background: "#FFFFFF",
        fontFamily: "var(--demo-sans)",
        color: "#0B0B0F",
        WebkitFontSmoothing: "antialiased",
        position: "relative",
      }}
    >
      <DemoHeader />

      <main
        className="wrap live-main"
        style={{
          paddingTop: 22,
          paddingBottom: 48,
          display: "flex",
          gap: 22,
          alignItems: "flex-start",
        }}
      >
        <section
          style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 22 }}
        >
          <h1 className="sr-only">Live du Grenier de Lyon : vinyles rares, années 70</h1>
          {/* Scène */}
          <div
            className="live-stage"
            style={{
              position: "relative",
              aspectRatio: "16 / 9",
              borderRadius: 26,
              overflow: "hidden",
              background: "#0B0B0F",
            }}
          >
            <img
              src={IMG.liveVinyls}
              alt="Disque vinyle présenté en direct"
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "cover",
                objectPosition: "50% 38%",
              }}
            />
            <span
              style={{
                position: "absolute",
                inset: 0,
                background:
                  "linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)",
              }}
            />

            <div
              className="live-top"
              style={{
                position: "absolute",
                top: 18,
                left: 18,
                right: 18,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    background: "#D93026",
                    color: "#FFFFFF",
                    fontSize: 12,
                    fontWeight: 600,
                    letterSpacing: "0.06em",
                    padding: "7px 11px 7px 9px",
                    borderRadius: 999,
                  }}
                >
                  <span
                    style={{ width: 6, height: 6, borderRadius: "50%", background: "#FFFFFF" }}
                  />
                  EN DIRECT
                </span>
                <span
                  className="gl m"
                  style={{ fontSize: 13, padding: "7px 11px", borderRadius: 999 }}
                >
                  1 284
                </span>
                <span
                  className="gl"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "4px 4px 4px 6px",
                    borderRadius: 999,
                  }}
                >
                  <span
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      background: "#FFFFFF",
                      color: "#0B0B0F",
                      display: "grid",
                      placeItems: "center",
                      fontSize: 11,
                      fontWeight: 700,
                    }}
                  >
                    GL
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Le Grenier de Lyon</span>
                  <button
                    type="button"
                    className="rm"
                    onClick={() => {
                      setFollow(!follow);
                    }}
                    style={
                      follow
                        ? { background: "rgba(255,255,255,0.2)", color: "#FFFFFF" }
                        : { background: "#FFFFFF", color: "#0B0B0F" }
                    }
                  >
                    {follow ? "Abonné" : "Suivre"}
                  </button>
                </span>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="gl"
                  onClick={() => {
                    setMuted(!muted);
                  }}
                  aria-label={muted ? "Activer le son" : "Couper le son"}
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: "50%",
                    border: 0,
                    display: "grid",
                    placeItems: "center",
                    cursor: "pointer",
                  }}
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M4 9.5v5h3.5L12 18.5V5.5L7.5 9.5z" fill="#FFFFFF" />
                    <path
                      d={
                        muted
                          ? "M16 9.5l5 5M21 9.5l-5 5"
                          : "M15.5 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"
                      }
                    />
                  </svg>
                </button>
                <button
                  type="button"
                  className="gl"
                  aria-label="Plein écran"
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: "50%",
                    border: 0,
                    display: "grid",
                    placeItems: "center",
                    cursor: "pointer",
                  }}
                >
                  <svg
                    width="17"
                    height="17"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Barre d'enchère */}
            <div
              className="gl live-bar"
              style={{
                position: "absolute",
                left: 18,
                right: 18,
                bottom: 18,
                borderRadius: 22,
                padding: "14px 16px",
                display: "flex",
                alignItems: "center",
                gap: 18,
              }}
            >
              <img
                src={IMG.vinyl}
                alt=""
                style={{
                  width: 58,
                  height: 58,
                  borderRadius: 14,
                  objectFit: "cover",
                  flex: "none",
                }}
              />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12, opacity: 0.75 }}>
                  Lot 14 sur 38 · bon état · vidéo de vérification jointe
                </div>
                <div
                  style={{
                    fontSize: 17,
                    fontWeight: 600,
                    letterSpacing: "-0.015em",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  Soul Sessions, pressage original 1972
                </div>
                <div
                  style={
                    mine
                      ? { fontSize: 13, marginTop: 2, color: "#7DF0A8", fontWeight: 600 }
                      : { fontSize: 13, marginTop: 2, opacity: 0.8 }
                  }
                >
                  {mine ? "Vous êtes le meilleur enchérisseur" : "Meilleure offre : hanna.s"}
                </div>
              </div>
              <div style={{ textAlign: "right", flex: "none" }}>
                <div className="m" style={{ fontSize: 30, letterSpacing: "-0.03em" }}>
                  {euros(price)}
                </div>
                <div className="m" style={{ fontSize: 12, opacity: 0.75 }}>
                  reste 0:18
                </div>
              </div>
              <div className="live-bids" style={{ display: "flex", gap: 6, flex: "none" }}>
                <button type="button" className="qb" onClick={bidBy(2)}>
                  +2
                </button>
                <button type="button" className="qb" onClick={bidBy(5)}>
                  +5
                </button>
                <button type="button" className="qb" onClick={bidBy(10)}>
                  +10
                </button>
                <button
                  type="button"
                  onClick={bidBy(2)}
                  style={{
                    height: 44,
                    padding: "0 20px",
                    borderRadius: 999,
                    border: 0,
                    background: "#1D2BFF",
                    color: "#FFFFFF",
                    font: "600 15px var(--demo-sans)",
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                    boxShadow: "0 8px 20px -8px rgba(29,43,255,0.9)",
                  }}
                >
                  Enchérir <span className="m">{euros(price + 2)}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Prochains passages */}
          <div>
            <div
              className="live-next-head"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginBottom: 14,
              }}
            >
              <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.03em" }}>
                Prochains passages
              </h2>
              <span style={{ fontSize: 14, color: "#6E6E73" }}>
                Ventes du live :{" "}
                <b className="m" style={{ color: "#0B0B0F" }}>
                  3 410 €
                </b>{" "}
                · 13 lots adjugés · tout payé dans TROVÉLYA
              </span>
            </div>
            <div
              className="live-next"
              style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 16 }}
            >
              {NEXT.map((n, i) => {
                const on = remind[i] === true;
                return (
                  <div key={n.t} className="nx">
                    <span className="im">
                      <img
                        src={IMG.vinyl}
                        alt={n.t}
                        style={{ width: "100%", height: "100%", objectFit: "cover", ...n.crop }}
                      />
                      <span
                        className="m"
                        style={{
                          position: "absolute",
                          left: 8,
                          top: 8,
                          fontSize: 11,
                          padding: "4px 8px",
                          borderRadius: 999,
                          background: "rgba(11,11,15,0.72)",
                          color: "#FFFFFF",
                        }}
                      >
                        {n.when}
                      </span>
                    </span>
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 500,
                        color: "#3A3A3F",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {n.t}
                    </span>
                    <span
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span className="m" style={{ fontSize: 14 }}>
                        {euros(n.p)}
                      </span>
                      <button
                        type="button"
                        className="rm"
                        onClick={() => {
                          setRemind({ ...remind, [i]: !on });
                        }}
                        style={
                          on
                            ? { background: "rgba(29,43,255,0.1)", color: "#1420C8" }
                            : { background: "#F2F2F7", color: "#0B0B0F" }
                        }
                      >
                        {on ? "Rappel activé" : "Me rappeler"}
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Chat */}
        <aside
          className="live-chat"
          style={{
            flex: "none",
            width: 360,
            height: 780,
            borderRadius: 26,
            background: "#F5F5F8",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "16px 18px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderBottom: "0.5px solid rgba(60,60,67,0.14)",
            }}
          >
            <span style={{ fontSize: 16, fontWeight: 600 }}>Chat du live</span>
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                color: "#155C33",
                fontWeight: 600,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 2.8 4.6 5.8v6.1c0 4.6 3.1 7.8 7.4 9.3 4.3-1.5 7.4-4.7 7.4-9.3V5.8z"
                  fill="#1E7A45"
                />
              </svg>
              Chat protégé
            </span>
          </div>
          <div
            aria-live="polite"
            style={{
              flex: 1,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              justifyContent: "flex-end",
              gap: 12,
              padding: "16px 18px",
            }}
          >
            {msgs.map((m) => (
              <div key={m.id} className="msg" style={WRAP[m.k]}>
                <span className="av" style={{ background: AVATAR[m.k] }}>
                  {m.k === "sys" ? "T" : m.n.slice(0, 2).toUpperCase()}
                </span>
                <div style={{ minWidth: 0 }}>
                  <span style={{ fontWeight: 600, color: NAME_COLOR[m.k] }}>{m.n}</span>{" "}
                  <span
                    style={m.k === "b" || m.k === "me" ? { fontWeight: 600 } : { color: "#3A3A3F" }}
                  >
                    {m.t}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <div style={{ padding: 12, borderTop: "0.5px solid rgba(60,60,67,0.14)" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                height: 46,
                padding: "0 6px 0 16px",
                borderRadius: 999,
                background: "#FFFFFF",
                boxShadow: "0 0 0 0.5px rgba(60,60,67,0.2)",
              }}
            >
              <label htmlFor="lc" className="sr-only">
                Écrire dans le chat
              </label>
              <input
                id="lc"
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                }}
                placeholder="Écrire un message…"
                style={{
                  flex: 1,
                  minWidth: 0,
                  border: 0,
                  background: "transparent",
                  font: "15px var(--demo-sans)",
                  color: "#0B0B0F",
                }}
              />
              <button
                type="button"
                onClick={send}
                aria-label="Envoyer"
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  border: 0,
                  background: "#1D2BFF",
                  display: "grid",
                  placeItems: "center",
                  cursor: "pointer",
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
                  <path d="M12 19V5M6 11l6-6 6 6" />
                </svg>
              </button>
            </div>
            <div style={{ fontSize: 11, color: "#6E6E73", margin: "8px 6px 0" }}>
              Essayez d&apos;écrire un numéro ou « Lydia » : TROVÉLYA le masque.
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
}
