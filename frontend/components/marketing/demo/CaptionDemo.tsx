"use client";

/* eslint-disable @next/next/no-img-element */
import { memo, useRef, type CSSProperties } from "react";
import s from "./ShortPulseDemo.module.css";
import {
  Cursor,
  Icon,
  Phone,
  Shell,
  SHELL,
  StudioHead,
  back,
  clamp,
  inOut,
  out,
  prog,
  showHide,
  typed,
  useDemoClock,
  useStageScale,
  type Locale,
  type Path,
} from "./kit";

/**
 * Caption or dub my video — drop in a talking-head clip, pick another
 * language, and it comes back transcribed, translated, re-voiced and
 * captioned.
 *
 * Labels are the studio's own (messages: studio.upload). It dubs, so it
 * charges a dub: DUB_COST, 4 credits, not the 2 of captions alone.
 */

export type CaptionDemoAssets = {
  /** A vertical still of someone talking to camera (a frame of your own sample works best). */
  still: string;
  /** Optional muted video of the same, used instead of the still. */
  video?: string;
};

type Props = {
  assets: CaptionDemoAssets;
  locale?: Locale;
  accent?: string;
  className?: string;
  time?: number;
  speed?: number;
  fadeEdges?: boolean;
};

const COPY = {
  tr: {
    title: ["", "Elinde olan", " bir video."] as [string, string, string],
    sub: "Her söz zamanlanıp yazılır — istersen başka bir dilde yeniden seslendirilir.",
    drop: "Videoyu buraya bırak",
    dropHint: "MP4, MOV, WebM veya MKV · en fazla 1GB · ses kanalı gerekir",
    fileMeta: "0:20 · 1080×1920 · ses var",
    uploaded: "yüklendi",
    cut: "Kesitlere böl",
    cutOpts: ["Bölme — bütün kalsın", "2", "3", "4", "5"],
    speak: "Başka bir dilde seslendir",
    langs: ["Seslendirme — sadece altyazı ekle", "English", "Türkçe", "Español", "Français", "Deutsch", "Português", "Polski"],
    target: 2,
    capsIn: "Altyazı dili",
    spoken: "Konuşulan dil",
    rows: [
      ["Görünüm", "klasik"],
      ["Son dokunuşlar", "Bip kapalı"],
    ],
    placeholder: "Videon seçtiğin anda burada görünür.",
    burned: "9:16 · ALTYAZI GÖMÜLÜ",
    cost: "4 kredi",
    button: "Seslendir",
    back: "Kütüphane",
    tabs: ["Döküm", "Düzenle"],
    output: "ÇIKTI",
    statuses: ["dinleniyor", "çevriliyor", "seslendiriliyor", "altyazılar gömülüyor", "hazır"],
    steps: ["Konuşmayı yazıya dök", "Türkçe'ye çevir", "Yeni ses", "Altyazıları göm"],
    download: ".mp4 indir",
    share: "Paylaş",
    from: "EN",
    to: "TR",
    voice: "Türkçe ses",
    words: "kelime",
    orig: [
      "Most people check their phone 96 times a day.",
      "But here's what nobody tells you.",
      "It's not the phone. It's the boredom.",
      "Sit with it for ten minutes a day.",
    ],
    dub: ["İnsanlar telefonuna günde 96 kez bakıyor.", "Ama kimsenin söylemediği bir şey var.", "Sorun telefon değil, can sıkıntısı.", "Günde on dakika onunla otur."],
    caps: [
      ["GÜNDE", "96", "KEZ", "TELEFONA", "BAKIYORUZ"],
      ["AMA", "KİMSE", "BUNU", "SÖYLEMİYOR"],
      ["SORUN", "TELEFON", "DEĞİL"],
      ["GÜNDE", "ON", "DAKİKA", "OTUR"],
    ],
    hi: [1, 3, 1, 1],
  },
  en: {
    title: ["A video you ", "already have", "."] as [string, string, string],
    sub: "Every spoken word gets timed and burned in — or spoken again in another language.",
    drop: "Drop a video here",
    dropHint: "MP4, MOV, WebM or MKV · up to 1GB · needs an audio track",
    fileMeta: "0:20 · 1080×1920 · audio",
    uploaded: "uploaded",
    cut: "Cut it into clips",
    cutOpts: ["Don't — keep it whole", "2", "3", "4", "5"],
    speak: "Speak it in another language",
    langs: ["Don't — just add captions", "English", "Türkçe", "Español", "Français", "Deutsch", "Português", "Polski"],
    target: 3,
    capsIn: "Captions in",
    spoken: "The language spoken",
    rows: [
      ["Look", "classic"],
      ["Finishing touches", "Bleep off"],
    ],
    placeholder: "Your video appears here as soon as you pick it.",
    burned: "9:16 · CAPTIONS BURNED IN",
    cost: "4 credits",
    button: "Dub it",
    back: "Library",
    tabs: ["Transcript", "Edit"],
    output: "OUTPUT",
    statuses: ["listening", "translating", "re-voicing", "burning in captions", "ready"],
    steps: ["Transcribe speech", "Translate to Spanish", "New voice", "Burn in captions"],
    download: "Download .mp4",
    share: "Share",
    from: "EN",
    to: "ES",
    voice: "Spanish voice",
    words: "words",
    orig: [
      "Most people check their phone 96 times a day.",
      "But here's what nobody tells you.",
      "It's not the phone. It's the boredom.",
      "Sit with it for ten minutes a day.",
    ],
    dub: ["Miramos el móvil 96 veces al día.", "Pero nadie te cuenta esto.", "No es el móvil. Es el aburrimiento.", "Quédate con él diez minutos al día."],
    caps: [
      ["MIRAMOS", "EL", "MÓVIL", "96", "VECES"],
      ["NADIE", "TE", "CUENTA", "ESTO"],
      ["ES", "EL", "ABURRIMIENTO"],
      ["DIEZ", "MINUTOS", "AL", "DÍA"],
    ],
    hi: [3, 2, 2, 0],
  },
  pl: {
    title: ["Film, który ", "już masz", "."] as [string, string, string],
    sub: "Każde słowo dostaje swój czas i trafia na ekran — albo zostaje przeczytane w innym języku.",
    drop: "Upuść tutaj film",
    dropHint: "MP4, MOV, WebM lub MKV · do 1 GB · wymaga ścieżki dźwiękowej",
    fileMeta: "0:20 · 1080×1920 · dźwięk",
    uploaded: "wysłano",
    cut: "Potnij na klipy",
    cutOpts: ["Nie tnij — zostaw w całości", "2", "3", "4", "5"],
    speak: "Przeczytaj w innym języku",
    langs: ["Nie — tylko napisy", "English", "Türkçe", "Español", "Français", "Deutsch", "Português", "Polski"],
    target: 7,
    capsIn: "Napisy w języku",
    spoken: "Język mówiony",
    rows: [
      ["Wygląd", "klasyczne"],
      ["Wykończenie", "Bez wypikania"],
    ],
    placeholder: "Twój film pojawi się tu, gdy tylko go wybierzesz.",
    burned: "9:16 · NAPISY WTOPIONE",
    cost: "4 kredyty",
    button: "Zdubbinguj",
    back: "Biblioteka",
    tabs: ["Scenariusz", "Edycja"],
    output: "WYNIK",
    statuses: ["słuchanie", "tłumaczenie", "nowy lektor", "wtapianie napisów", "gotowe"],
    steps: ["Transkrypcja mowy", "Tłumaczenie na polski", "Nowy lektor", "Wtopienie napisów"],
    download: "Pobierz .mp4",
    share: "Udostępnij",
    from: "EN",
    to: "PL",
    voice: "Polski lektor",
    words: "słów",
    orig: [
      "Most people check their phone 96 times a day.",
      "But here's what nobody tells you.",
      "It's not the phone. It's the boredom.",
      "Sit with it for ten minutes a day.",
    ],
    dub: ["Sprawdzamy telefon 96 razy dziennie.", "Ale nikt ci nie mówi jednej rzeczy.", "To nie telefon. To nuda.", "Posiedź z nią dziesięć minut dziennie."],
    caps: [
      ["SPRAWDZAMY", "TELEFON", "96", "RAZY"],
      ["NIKT", "CI", "TEGO", "NIE", "MÓWI"],
      ["TO", "NIE", "TELEFON"],
      ["DZIESIĘĆ", "MINUT", "DZIENNIE"],
    ],
    hi: [2, 0, 2, 1],
  },
  de: {
    title: ["Ein Video, das du ", "schon hast", "."] as [string, string, string],
    sub: "Jedes gesprochene Wort wird getimt und eingebrannt — oder in einer anderen Sprache neu gesprochen.",
    drop: "Video hier ablegen",
    dropHint: "MP4, MOV, WebM oder MKV · bis 1 GB · braucht eine Tonspur",
    fileMeta: "0:20 · 1080×1920 · Ton",
    uploaded: "hochgeladen",
    cut: "In Clips schneiden",
    cutOpts: ["Nicht — am Stück lassen", "2", "3", "4", "5"],
    speak: "In einer anderen Sprache sprechen",
    langs: ["Nicht — nur Untertitel", "English", "Türkçe", "Español", "Français", "Deutsch", "Português", "Polski"],
    target: 5,
    capsIn: "Untertitel auf",
    spoken: "Die gesprochene Sprache",
    rows: [
      ["Aussehen", "klassisch"],
      ["Letzter Schliff", "Piepen aus"],
    ],
    placeholder: "Dein Video erscheint hier, sobald du es auswählst.",
    burned: "9:16 · UNTERTITEL EINGEBRANNT",
    cost: "4 Credits",
    button: "Synchronisieren",
    back: "Bibliothek",
    tabs: ["Ablauf", "Bearbeiten"],
    output: "AUSGABE",
    statuses: ["hört zu", "übersetzt", "spricht neu", "brennt Untertitel ein", "fertig"],
    steps: ["Sprache transkribieren", "Ins Deutsche übersetzen", "Neue Stimme", "Untertitel einbrennen"],
    download: ".mp4 laden",
    share: "Teilen",
    from: "EN",
    to: "DE",
    voice: "Deutsche Stimme",
    words: "Wörter",
    orig: [
      "Most people check their phone 96 times a day.",
      "But here's what nobody tells you.",
      "It's not the phone. It's the boredom.",
      "Sit with it for ten minutes a day.",
    ],
    dub: ["Wir schauen 96 Mal am Tag aufs Handy.", "Aber das sagt dir niemand.", "Es ist nicht das Handy. Es ist die Langeweile.", "Halte sie zehn Minuten am Tag aus."],
    caps: [
      ["96", "MAL", "AM", "TAG", "AUFS", "HANDY"],
      ["DAS", "SAGT", "DIR", "NIEMAND"],
      ["ES", "IST", "DIE", "LANGEWEILE"],
      ["ZEHN", "MINUTEN", "AM", "TAG"],
    ],
    hi: [0, 3, 3, 0],
  },
};

const P0 = 5600; // project page
const PLAY = P0 + 6000;
const SEG = 1500;
export const CAPTION_DEMO_LENGTH = P0 + 12800;

const menuY = (i: number) => 424 + 6 + i * 26 + 13;

function pathFor(target: number): Path {
  const y = menuY(target);
  return [
    [0, 1000, 250],
    [500, 1000, 250],
    [1400, 452, 241],
    [2600, 452, 241],
    [3300, 452, 403],
    [3500, 452, 403],
    [4200, 452, y],
    [4700, 452, y],
    [5300, 1023, 672],
    [5600, 1023, 672],
    [6600, 980, 560],
  ];
}
const CLICKS = [1450, 3350, 4250, 5350];
const HELD: [number, number][] = [[500, 1450]];

function CaptionDemo({ assets, locale = "en", accent = "rgb(var(--accent))", className, time, speed = 1, fadeEdges = true }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const scale = useStageScale(rootRef);
  const t = useDemoClock(time, speed, rootRef, CAPTION_DEMO_LENGTH, PLAY + 400);
  const L = (COPY[locale] ?? COPY.en) as L;
  const path = pathFor(L.target);

  const loopFade = fadeEdges ? Math.min(prog(t, 0, 450), 1 - prog(t, CAPTION_DEMO_LENGTH - 600, CAPTION_DEMO_LENGTH)) : 1;
  const aO = 1 - prog(t, 5300, 5650);
  const bO = prog(t, 5550, 5900);
  const credits = Math.round(146 - 4 * inOut(prog(t, 5400, 5900)));

  return (
    <div
      ref={rootRef}
      className={`${s.root} ${className ?? ""}`}
      style={{ "--sp-accent": accent } as CSSProperties}
      role="img"
      aria-label="ShortPulse demo: upload a video, choose another language, and get it transcribed, translated, re-voiced and captioned."
    >
      <div className={s.stage} style={{ transform: `scale(${scale})`, opacity: loopFade }}>
        <div className={s.grid} />
        <div className={s.wash} />
        {aO > 0 && <Upload t={t} o={aO} L={L} assets={assets} locale={locale} />}
        {bO > 0 && <Result t={t} o={bO} L={L} assets={assets} />}
        <Shell locale={locale} credits={credits} pillY={70} activeNav={0} header={t < P0 ? SHELL[locale].headers[0] : SHELL[locale].headers[1]} />
        <Cursor t={t} path={path} clicks={CLICKS} pressed={HELD} />
        {t >= 500 && t < 1450 && <FileGhost t={t} path={path} assets={assets} />}
      </div>
    </div>
  );
}

export default memo(CaptionDemo);

type L = (typeof COPY)["tr"];

function FileGhost({ t, path, assets }: { t: number; path: Path; assets: CaptionDemoAssets }) {
  // follows the cursor while it is held
  const i = path.findIndex((p) => p[0] > t);
  const [t0, x0, y0] = path[Math.max(0, i - 1)];
  const [t1, x1, y1] = path[i] ?? path[path.length - 1];
  const k = inOut(prog(t, t0, t1));
  const x = x0 + (x1 - x0) * k;
  const y = y0 + (y1 - y0) * k;
  return (
    <div className={s.fileGhost} style={{ left: x - 20, top: y - 30, opacity: out(prog(t, 500, 700)), transform: "rotate(-2deg)" }}>
      <img src={assets.still} alt="" />
      <div>
        street-talk.mp4
        <span>0:20 · 24 MB</span>
      </div>
    </div>
  );
}

function Upload({ t, o, L, assets, locale }: { t: number; o: number; L: L; assets: CaptionDemoAssets; locale: Locale }) {
  const enter = out(prog(t, 80, 520));
  const over = t >= 1000 && t < 1450;
  const dropped = t >= 1450;
  const up = prog(t, 1500, 2300);
  const phoneIn = out(prog(t, 1700, 2200));
  const menu = showHide(t, 3380, 4400, 180);
  const hover = t < 3500 ? 0 : Math.min(L.target, Math.floor(prog(t, 3500, 4150) * (L.target + 0.99)));
  const chosen = t >= 4250;
  const btnPress = t >= 5350 && t < 5500 ? 0.94 : 1;

  return (
    <div className={s.scene} style={{ opacity: o, transform: `translateY(${(1 - enter) * 10}px)` }}>
      <StudioHead locale={locale} title={L.title} sub={L.sub} mode={1} />

      <div className={s.card} style={{ left: 214, top: 176, width: 476, height: 410 }} />
      {!dropped ? (
        <div className={`${s.drop} ${over ? s.dropOver : ""}`} style={{ left: 230, top: 192, width: 444, height: 98 }}>
          <Icon name="upload" size={18} style={{ color: over ? "var(--sp-accent)" : "var(--sp-muted)" }} />
          {L.drop}
          <small>{L.dropHint}</small>
        </div>
      ) : (
        <div className={s.drop} style={{ left: 230, top: 192, width: 444, height: 98, borderStyle: "solid", borderColor: "var(--sp-line-strong)", alignItems: "stretch" }}>
          <div className={s.abs} style={{ left: 14, top: 18, width: 34, height: 60, borderRadius: 5, overflow: "hidden" }}>
            <img src={assets.still} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </div>
          <div className={s.abs} style={{ left: 60, top: 20, fontSize: 13 }}>
            street-talk.mp4
          </div>
          <div className={`${s.abs} ${s.mono}`} style={{ left: 60, top: 40, fontSize: 10.5, color: "var(--sp-faint)" }}>
            {L.fileMeta}
          </div>
          <div className={s.abs} style={{ left: 60, top: 66, width: 300, height: 4, borderRadius: 3, background: "rgba(255,255,255,.08)" }}>
            <div style={{ width: `${up * 100}%`, height: "100%", borderRadius: 3, background: "var(--sp-accent)" }} />
          </div>
          {up >= 1 && (
            <div className={s.abs} style={{ left: 372, top: 58, display: "flex", gap: 5, alignItems: "center", fontSize: 11, color: "var(--sp-green)", opacity: out(prog(t, 2300, 2500)) }}>
              <Icon name="check" size={12} style={{ strokeWidth: 2.6 }} /> {L.uploaded}
            </div>
          )}
        </div>
      )}

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 304 }}>
        {L.cut}
      </div>
      <div className={s.pick} style={{ left: 230, top: 324 }}>
        {L.cutOpts.map((c, i) => (
          <span key={i} className={`${s.chip} ${i === 0 ? s.chipOn : ""}`} style={{ borderColor: i === 0 ? "var(--sp-accent)" : undefined, minWidth: i === 0 ? 0 : 40 }}>
            {c}
          </span>
        ))}
      </div>

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 366 }}>
        {L.speak}
      </div>
      <div className={s.select} style={{ left: 230, top: 386, width: 444, height: 34, borderColor: menu > 0 ? "var(--sp-accent)" : undefined }}>
        <span style={{ color: chosen ? "var(--sp-text)" : "var(--sp-muted)", display: "flex", gap: 8, alignItems: "center" }}>
          {chosen && <Icon name="mic" size={13} style={{ color: "var(--sp-accent)" }} />}
          {chosen ? L.langs[L.target] : L.langs[0]}
        </span>
        <Icon name="chevron" size={13} style={{ transform: "rotate(90deg)", color: "var(--sp-faint)" }} />
      </div>

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 434 }}>
        {L.capsIn}
      </div>
      <div className={s.select} style={{ left: 230, top: 454, width: 444, height: 34 }}>
        <span style={{ color: "var(--sp-muted)" }}>{L.spoken}</span>
        <Icon name="chevron" size={13} style={{ transform: "rotate(90deg)", color: "var(--sp-faint)" }} />
      </div>
      {L.rows.map(([k, v], i) => (
        <div key={k} className={s.setRow} style={{ left: 230, top: 502 + i * 38, width: 444, height: 32 }}>
          <Icon name={i === 0 ? "palette" : "wand"} size={14} style={{ color: "var(--sp-muted)" }} />
          {k}
          <small>{v}</small>
          <Icon name="chevron" size={13} style={{ color: "var(--sp-faint)", marginLeft: 0 }} />
        </div>
      ))}

      {menu > 0 && (
        <div className={s.menu} style={{ left: 230, top: 424, width: 444, opacity: menu, transform: `translateY(${(1 - menu) * -6}px)` }}>
          {L.langs.map((lg, i) => (
            <div key={lg} className={`${s.menuItem} ${i === hover && t >= 3500 ? s.menuItemOn : ""}`}>
              {lg}
              {i === 0 && !chosen && <Icon name="check" size={12} />}
            </div>
          ))}
        </div>
      )}

      {/* preview */}
      <div className={s.card} style={{ left: 710, top: 176, width: 386, height: 410 }} />
      {phoneIn > 0 ? (
        <div style={{ opacity: phoneIn }}>
          <Phone x={813} y={192} w={180} h={320} src={assets.still} style={1} radius={12} kb={0.2} />
          {chosen && (
            <div className={s.voice} style={{ left: 821, top: 200, opacity: out(prog(t, 4250, 4500)) }}>
              <Icon name="mic" size={11} /> {L.voice}
            </div>
          )}
        </div>
      ) : (
        <div className={s.phone} style={{ left: 813, top: 192, width: 180, height: 320, display: "grid", placeItems: "center", textAlign: "center", padding: 24, color: "var(--sp-faint)", fontSize: 11.5 }}>
          <div>
            <Icon name="film" size={18} />
            <div style={{ marginTop: 8 }}>{L.placeholder}</div>
          </div>
        </div>
      )}
      <div className={`${s.abs} ${s.mono}`} style={{ left: 710, width: 386, top: 530, textAlign: "center", fontSize: 10.5, letterSpacing: "0.18em", color: "var(--sp-faint)" }}>
        {L.burned}
      </div>

      <div className={s.bottomBar}>
        <div className={s.abs} style={{ left: 24, top: 19, display: "flex", gap: 6, alignItems: "center", color: "var(--sp-muted)", fontSize: 12.5 }}>
          <Icon name="coins" size={13} /> <b style={{ color: "var(--sp-text)", fontWeight: 500 }}>{L.cost}</b> · 146 {SHELL[locale].left}
        </div>
      </div>
      <div className={`${s.btn} ${s.btnAccent}`} style={{ left: 950, top: 655, width: 146, opacity: dropped ? 1 : 0.45, transform: `scale(${btnPress})` }}>
        <Icon name="type" size={14} /> {L.button}
      </div>
    </div>
  );
}

function Result({ t, o, L, assets }: { t: number; o: number; L: L; assets: CaptionDemoAssets }) {
  const b = t - P0;
  const enter = out(prog(b, 0, 400));
  const stepDone = [2000, 3600, 5000, 5800];
  const stepStart = [0, 2000, 3600, 5000];
  const statusIdx = b < 2000 ? 0 : b < 3600 ? 1 : b < 5000 ? 2 : b < 5800 ? 3 : 4;
  const ready = b >= 5800;
  const p = t - PLAY;
  const playing = p >= 0 && p < 4 * SEG;
  const seg = playing ? Math.floor(p / SEG) : p >= 4 * SEG ? 3 : 0;
  const local = playing ? (p % SEG) / SEG : 0;
  const words = b >= 5000 ? L.caps[seg] : undefined;
  const wordIn = (i: number) => {
    if (!playing && p < 0) return prog(b, 5100 + i * 110, 5260 + i * 110);
    if (!playing) return 1;
    const n = L.caps[seg].length;
    const wt = seg * SEG + 80 + i * (1000 / n);
    return prog(p, wt, wt + 160);
  };
  const waveO = showHide(b, 3600, 5200, 250);

  return (
    <div className={s.scene} style={{ opacity: o, transform: `translateY(${(1 - enter) * 10}px)` }}>
      <div className={s.abs} style={{ left: 214, top: 58, display: "flex", gap: 8, alignItems: "center", color: "var(--sp-muted)", fontSize: 13 }}>
        <Icon name="back" size={14} /> {L.back}
      </div>
      <div className={s.abs} style={{ left: 214, top: 86, display: "flex", gap: 4, padding: 3, borderRadius: 10, border: "1px solid var(--sp-line)" }}>
        <span className={`${s.chip} ${s.chipOn}`} style={{ border: 0 }}>
          <Icon name="doc" size={13} /> {L.tabs[0]}
        </span>
        <span className={s.chip} style={{ border: 0, background: "transparent" }}>
          {L.tabs[1]}
        </span>
      </div>

      <div className={s.card} style={{ left: 214, top: 134, width: 546, height: 506 }} />
      {L.orig.map((line, i) => {
        const top = 150 + i * 118;
        const a = 300 + i * 400;
        const appear = out(prog(b, a, a + 250));
        if (appear <= 0) return null;
        const d0 = 2100 + i * 350;
        const dub = typed(L.dub[i], b, d0, d0 + 450);
        const on = playing && seg === i;
        const karaoke = on ? local : p >= (i + 1) * SEG ? 1 : 0;
        const dubWords = dub.split(" ");
        return (
          <div key={i} className={`${s.row} ${on ? s.rowOn : ""}`} style={{ top, height: 108, opacity: appear }}>
            {on && <div className={s.rowBar} />}
            <div className={`${s.tc} ${s.mono} ${on ? "" : s.tcDim}`} style={{ left: 18, top: 14 }}>
              0:{String(i * 5).padStart(2, "0")}
            </div>
            <div className={s.abs} style={{ left: 76, top: 12, display: "flex", gap: 8, alignItems: "center", fontSize: 12.5, color: "var(--sp-faint)", whiteSpace: "nowrap" }}>
              <span className={s.tag}>{L.from}</span>
              {typed(line, b, a, a + 380)}
            </div>
            {dub && (
              <div className={s.abs} style={{ left: 76, top: 44, display: "flex", gap: 8, alignItems: "center", fontSize: 14, whiteSpace: "nowrap" }}>
                <span className={`${s.tag} ${s.tagAccent}`}>{L.to}</span>
                <span>
                  {dubWords.map((w, j) => (
                    <span key={j} style={{ color: karaoke > 0 && j / dubWords.length < karaoke ? "var(--sp-accent)" : undefined }}>
                      {w}{" "}
                    </span>
                  ))}
                </span>
              </div>
            )}
            {b >= d0 + 450 && (
              <div className={`${s.abs} ${s.mono}`} style={{ left: 108, top: 76, fontSize: 10.5, color: "var(--sp-faint)", opacity: out(prog(b, d0 + 450, d0 + 700)) }}>
                {L.dub[i].split(" ").length} {L.words} · {(4.2 + i * 0.3).toFixed(1)}s
              </div>
            )}
          </div>
        );
      })}

      <div className={s.card} style={{ left: 780, top: 66, width: 316, height: 574 }} />
      <div className={`${s.abs} ${s.mono}`} style={{ left: 798, top: 82, fontSize: 11, letterSpacing: "0.22em", color: "var(--sp-faint)" }}>
        {L.output}
      </div>
      <div className={`${s.status} ${s.mono}`} style={{ right: 1120 - 1080, top: 81, color: ready ? "var(--sp-green)" : "var(--sp-muted)" }}>
        <span className={s.dot} style={{ background: ready ? "var(--sp-green)" : "var(--sp-accent)", opacity: ready ? 1 : 0.5 + 0.5 * Math.abs(Math.sin(b / 300)) }} />
        {L.statuses[statusIdx]}
      </div>
      <Phone
        x={839}
        y={106}
        w={198}
        h={352}
        src={assets.still}
        kb={playing ? (seg % 2 ? 1.4 : 0.2) + local * 0.15 : 0.2}
        words={words}
        hi={L.hi[seg]}
        wordIn={wordIn}
        style={1}
        wave={waveO}
        phase={b}
        progress={p >= 0 ? clamp(p / (4 * SEG)) : undefined}
      />
      {b >= 5000 && (
        <div className={s.voice} style={{ left: 847, top: 114, opacity: out(prog(b, 5000, 5300)) }}>
          <Icon name="mic" size={11} /> {L.voice}
        </div>
      )}
      {(["doc", "refresh", "mic", "type"] as const).map((ic, i) => {
        const done = b >= stepDone[i];
        const active = b >= stepStart[i] && !done;
        return (
          <div key={ic} className={`${s.step} ${done ? s.stepDone : ""}`} style={{ left: 798, top: 474 + i * 26, width: 280 }}>
            <Icon name={ic} size={14} />
            {L.steps[i]}
            <span className={s.stepRight}>
              {done ? (
                <span className={s.tick} style={{ transform: `scale(${back(prog(b, stepDone[i], stepDone[i] + 250))})` }}>
                  <Icon name="check" size={10} style={{ strokeWidth: 3 }} />
                </span>
              ) : active ? (
                <span className={s.spinner} />
              ) : (
                <span className={s.waiting} />
              )}
            </span>
          </div>
        );
      })}
      <div className={`${s.btn} ${s.btnGhost}`} style={{ left: 798, top: 586, width: 134, opacity: ready ? 1 : 0.4, fontWeight: 500, fontSize: 12.5 }}>
        <Icon name="download" size={13} /> {L.download}
      </div>
      <div className={`${s.btn} ${s.btnAccent}`} style={{ left: 944, top: 586, width: 134, opacity: ready ? 1 : 0.4 }}>
        <Icon name="send" size={13} /> {L.share}
      </div>
    </div>
  );
}
