"use client";

/* eslint-disable @next/next/no-img-element */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import s from "./ShortPulseDemo.module.css";

/**
 * ShortPulseDemo — a looping product demo for the landing page.
 *
 * Drawn, not recorded: every panel is markup laid out at 1120x700 and
 * scaled to fit, so it stays sharp at any width and follows the accent
 * picker. It walks the real flow and must stay true to it — the price is
 * stock_media's (2 credits, see services/credits.py), and TikTok says
 * "sent to drafts" because the video.upload scope posts to the inbox.
 * Studio (pick a trend, style the captions, generate) → Project (script,
 * stock footage, voice, captions, then the short plays) → Share to YouTube
 * and TikTok → the new video lands in the Library.
 *
 * Every frame is a pure function of one clock (`t`, ms). Pass `time` to
 * freeze a frame for screenshots.
 */

export type ShortPulseDemoAssets = {
  /** Five vertical stills (or frames from a real render), one per scene, in order. */
  scenes: [string, string, string, string, string];
  /** Optional cards for the rest of the Library grid: a poster and its title. */
  library?: { src: string; title: string }[];
  /** Optional avatar for the account row in the rail. */
  avatar?: string;
};

type Props = {
  assets: ShortPulseDemoAssets;
  locale?: "tr" | "en" | "pl" | "de";
  /** Matches the app's accent picker. */
  accent?: string;
  className?: string;
  time?: number;
  speed?: number;
};

/* ------------------------------------------------------------------ */
/* Copy                                                                */
/* ------------------------------------------------------------------ */

const COPY = {
  tr: {
    nav: ["Stüdyo", "Kütüphane", "Dosyalarım", "Bağlantılar", "Krediler"],
    headers: ["STÜDYO", "PROJE", "KÜTÜPHANE"],
    credits: "kredi",
    hero: ["Bu ", "video", " ne hakkında?"],
    heroSub: "Bir konu yaz — gerisini senaryo yazarı, seslendirme ve kurgu halleder.",
    modes: ["Konudan üret", "Videomu altyazıla", "Kliplerimle edit"],
    trend: "Neler trend — video fikirleri",
    rising: "Yükseliyor",
    trendTitle: "Bilim merakı yükselişte",
    trendItems: ["Okyanus neden tuzlu? 20 saniyede bilim", "Uyurken beynimiz ne yapar?", "Bal neden hiç bozulmaz?"],
    use: "Kullan",
    idea: "Fikir",
    topic: "Konu",
    topicPh: "örn. insanların sana güvenmesini sağlayan 3 taktik",
    topicValue: "Okyanus neden tuzlu? 20 saniyede bilim",
    rows: ["Format & dil", "Görünüm", "Ses"],
    rowVals: ["9:16 · TR", "stok görüntü · {s} altyazı", "Varsayılan ses · müzik: sakin"],
    styles: ["Klasik", "Vurgulu", "Kutu"],
    preview: "Önizleme — altyazı stili canlı",
    thisRender: "Bu render",
    kv: [
      ["Format", "9:16 · 1080x1920"],
      ["Uzunluk", "15–25s"],
      ["Sahne", "5"],
      ["Maliyet", "2 kredi"],
    ],
    cost: "2 kredi",
    left: "kaldı",
    generate: "Video üret",
    back: "Kütüphane",
    tabs: ["Döküm", "Düzenle"],
    output: "ÇIKTI",
    statuses: ["senaryo yazılıyor", "görüntüler bulunuyor", "seslendiriliyor", "altyazılar ekleniyor", "hazır"],
    steps: ["Senaryo", "Stok görüntü · Pexels", "Seslendirme", "Altyazı & müzik"],
    download: ".mp4 indir",
    share: "Paylaş",
    shareTitle: "Paylaş",
    shareSub: "Bağlı hesaplar",
    yt: ["YouTube Shorts", "ShortPulse"],
    tt: ["TikTok", "ShortPulse"],
    descLabel: "Açıklama",
    desc: "Okyanus neden tuzlu? #bilim #shorts",
    send: "Gönder",
    sending: "gönderiliyor…",
    ytDone: "Shorts'a yüklendi",
    ttDone: "Taslaklara gönderildi",
    wrong: "yanlış mı?",
    regen: "yeniden üret",
    libTitle: "Videoların",
    libCount: (n: number) => `${n} proje`,
    newVideo: "Yeni video",
    filters: ["Tümü", "AI shortlar", "Yüklenen videolar", "Editler"],
    justNow: "az önce · 0:21 · 9:16",
    ago: (d: number) => `${d} gün önce · 0:2${d % 6} · 9:16`,
    libTitles: ["Ay yok olsaydı", "Dünya dönmeyi bıraksa", "Ahtapotun üç kalbi", "Kediler neden kutu sever", "Rüyalar nereden gelir", "Bal neden bozulmaz", "Işık ne kadar hızlı", "Polonya'da 5 gerçek", "Uyurken beynimiz"],
    hook: "Okyanusun her damlası tuz taşıyor.",
    lines: ["Yağmur, kayaları yavaş yavaş aşındırır.", "Nehirler bu mineralleri denize taşır.", "Güneş suyu buharlaştırır, tuz geride kalır.", "Milyonlarca yıl sonra okyanus tuzludur."],
    caps: [
      ["OKYANUSUN", "HER", "DAMLASI", "TUZ", "TAŞIR"],
      ["YAĞMUR", "KAYALARI", "AŞINDIRIR"],
      ["NEHİRLER", "MİNERALLERİ", "DENİZE", "TAŞIR"],
      ["SU", "BUHARLAŞIR,", "TUZ", "KALIR"],
      ["VE", "OKYANUS", "TUZLANIR"],
    ],
    hi: [3, 1, 1, 2, 2],
  },
  en: {
    nav: ["Studio", "Library", "My files", "Connections", "Credits"],
    headers: ["STUDIO", "PROJECT", "LIBRARY"],
    credits: "credits",
    hero: ["What's this ", "video", " about?"],
    heroSub: "Type a topic — the scriptwriter, voice and edit take it from there.",
    modes: ["From a topic", "Caption my video", "Edit my clips"],
    trend: "What's trending — video ideas",
    rising: "Rising",
    trendTitle: "Science curiosity is up",
    trendItems: ["Why is the ocean salty? Science in 20s", "What does the brain do while we sleep?", "Why does honey never spoil?"],
    use: "Use",
    idea: "Idea",
    topic: "Topic",
    topicPh: "e.g. 3 psychology tricks that make people trust you",
    topicValue: "Why is the ocean salty? Science in 20s",
    rows: ["Format & language", "Look", "Audio"],
    rowVals: ["9:16 · EN", "stock footage · {s} captions", "Default voice · music: calm"],
    styles: ["Classic", "Highlight", "Boxed"],
    preview: "Preview — caption style is live",
    thisRender: "This render",
    kv: [
      ["Format", "9:16 · 1080x1920"],
      ["Length", "15–25s"],
      ["Scenes", "5"],
      ["Cost", "2 credits"],
    ],
    cost: "2 credits",
    left: "left",
    generate: "Generate video",
    back: "Library",
    tabs: ["Breakdown", "Edit"],
    output: "OUTPUT",
    statuses: ["writing the script", "finding footage", "recording voice", "adding captions", "ready"],
    steps: ["Script", "Stock footage · Pexels", "Voiceover", "Captions & music"],
    download: "Download .mp4",
    share: "Share",
    shareTitle: "Share",
    shareSub: "Connected accounts",
    yt: ["YouTube Shorts", "ShortPulse"],
    tt: ["TikTok", "ShortPulse"],
    descLabel: "Description",
    desc: "Why is the ocean salty? #science #shorts",
    send: "Send",
    sending: "sending…",
    ytDone: "Uploaded to Shorts",
    ttDone: "Sent to drafts",
    wrong: "wrong?",
    regen: "regenerate",
    libTitle: "Your videos",
    libCount: (n: number) => `${n} projects`,
    newVideo: "New video",
    filters: ["All", "AI shorts", "Uploaded videos", "Edits"],
    justNow: "just now · 0:21 · 9:16",
    ago: (d: number) => `${d} days ago · 0:2${d % 6} · 9:16`,
    libTitles: ["If the Moon vanished", "If Earth stopped spinning", "An octopus has 3 hearts", "Why cats love boxes", "Where dreams come from", "Why honey never spoils", "How fast is light", "5 facts about Poland", "Your brain asleep"],
    hook: "Every drop of the ocean carries salt.",
    lines: ["Rain slowly wears the rocks away.", "Rivers carry those minerals to the sea.", "The sun lifts the water — the salt stays.", "Millions of years later, the sea is salty."],
    caps: [
      ["EVERY", "DROP", "CARRIES", "SALT"],
      ["RAIN", "WEARS", "DOWN", "ROCKS"],
      ["RIVERS", "CARRY", "MINERALS", "TO", "SEA"],
      ["WATER", "LEAVES,", "SALT", "STAYS"],
      ["AND", "THE", "SEA", "TURNS", "SALTY"],
    ],
    hi: [3, 3, 2, 2, 4],
  },
  pl: {
    nav: ["Studio", "Biblioteka", "Moje pliki", "Połączenia", "Kredyty"],
    headers: ["STUDIO", "PROJEKT", "BIBLIOTEKA"],
    credits: "kredytów",
    hero: ["O czym jest ten ", "film", "?"],
    heroSub: "Wpisz temat — scenariusz, lektor i montaż zrobią resztę.",
    modes: ["Z tematu", "Napisy do filmu", "Montaż z klipów"],
    trend: "Co jest na topie — pomysły na filmy",
    rising: "Rośnie",
    trendTitle: "Ciekawostki naukowe rosną",
    trendItems: ["Dlaczego ocean jest słony? Nauka w 20 s", "Co robi mózg, gdy śpimy?", "Dlaczego miód się nie psuje?"],
    use: "Użyj",
    idea: "Pomysł",
    topic: "Temat",
    topicPh: "np. 3 triki, dzięki którym ludzie ci ufają",
    topicValue: "Dlaczego ocean jest słony? Nauka w 20 s",
    rows: ["Format i język", "Wygląd", "Dźwięk"],
    rowVals: ["9:16 · PL", "materiał stockowy · napisy: {s}", "Domyślny głos · muzyka: spokojna"],
    styles: ["Klasyczne", "Wyróżnione", "W ramce"],
    preview: "Podgląd — styl napisów na żywo",
    thisRender: "Ten render",
    kv: [
      ["Format", "9:16 · 1080x1920"],
      ["Długość", "15–25s"],
      ["Sceny", "5"],
      ["Koszt", "2 kredyty"],
    ],
    cost: "2 kredyty",
    left: "zostało",
    generate: "Utwórz film",
    back: "Biblioteka",
    tabs: ["Scenariusz", "Edycja"],
    output: "WYNIK",
    statuses: ["pisanie scenariusza", "szukanie ujęć", "nagrywanie lektora", "dodawanie napisów", "gotowe"],
    steps: ["Scenariusz", "Materiał stockowy · Pexels", "Lektor", "Napisy i muzyka"],
    download: "Pobierz .mp4",
    share: "Udostępnij",
    shareTitle: "Udostępnij",
    shareSub: "Połączone konta",
    yt: ["YouTube Shorts", "ShortPulse"],
    tt: ["TikTok", "ShortPulse"],
    descLabel: "Opis",
    desc: "Dlaczego ocean jest słony? #nauka #shorts",
    send: "Wyślij",
    sending: "wysyłanie…",
    ytDone: "Wrzucone do Shorts",
    ttDone: "Wysłane do wersji roboczych",
    wrong: "źle?",
    regen: "wygeneruj ponownie",
    libTitle: "Twoje filmy",
    libCount: (n: number) => `${n} projektów`,
    newVideo: "Nowy film",
    filters: ["Wszystkie", "Shorty AI", "Wgrane filmy", "Montaże"],
    justNow: "przed chwilą · 0:21 · 9:16",
    ago: (d: number) => `${d} dni temu · 0:2${d % 6} · 9:16`,
    libTitles: ["Gdyby Księżyc zniknął", "Gdyby Ziemia się zatrzymała", "Ośmiornica ma 3 serca", "Czemu koty kochają pudełka", "Skąd się biorą sny", "Czemu miód się nie psuje", "Jak szybkie jest światło", "5 faktów o Polsce", "Mózg podczas snu"],
    hook: "Każda kropla oceanu niesie sól.",
    lines: ["Deszcz powoli kruszy skały.", "Rzeki niosą te minerały do morza.", "Słońce odparowuje wodę — sól zostaje.", "Po milionach lat ocean jest słony."],
    caps: [
      ["KAŻDA", "KROPLA", "NIESIE", "SÓL"],
      ["DESZCZ", "KRUSZY", "SKAŁY"],
      ["RZEKI", "NIOSĄ", "MINERAŁY", "DO", "MORZA"],
      ["WODA", "ODCHODZI,", "SÓL", "ZOSTAJE"],
      ["I", "OCEAN", "STAJE", "SIĘ", "SŁONY"],
    ],
    hi: [3, 2, 2, 2, 4],
  },
  de: {
    nav: ["Studio", "Bibliothek", "Meine Dateien", "Verbindungen", "Credits"],
    headers: ["STUDIO", "PROJEKT", "BIBLIOTHEK"],
    credits: "Credits",
    hero: ["Worum geht es in diesem ", "Video", "?"],
    heroSub: "Gib ein Thema ein — Skript, Sprecher und Schnitt übernehmen den Rest.",
    modes: ["Aus einem Thema", "Video untertiteln", "Clips schneiden"],
    trend: "Im Trend — Videoideen",
    rising: "Steigend",
    trendTitle: "Wissenschaft ist gefragt",
    trendItems: ["Warum ist das Meer salzig? Wissen in 20 s", "Was macht das Gehirn im Schlaf?", "Warum verdirbt Honig nie?"],
    use: "Nutzen",
    idea: "Idee",
    topic: "Thema",
    topicPh: "z. B. 3 Tricks, damit dir Menschen vertrauen",
    topicValue: "Warum ist das Meer salzig? Wissen in 20 s",
    rows: ["Format & Sprache", "Look", "Audio"],
    rowVals: ["9:16 · DE", "Stockmaterial · {s} Untertitel", "Standardstimme · Musik: ruhig"],
    styles: ["Klassisch", "Hervorgehoben", "Box"],
    preview: "Vorschau — Untertitelstil live",
    thisRender: "Dieser Render",
    kv: [
      ["Format", "9:16 · 1080x1920"],
      ["Länge", "15–25s"],
      ["Szenen", "5"],
      ["Kosten", "2 Credits"],
    ],
    cost: "2 Credits",
    left: "übrig",
    generate: "Video erstellen",
    back: "Bibliothek",
    tabs: ["Ablauf", "Bearbeiten"],
    output: "AUSGABE",
    statuses: ["Skript wird geschrieben", "Aufnahmen werden gesucht", "Sprecher nimmt auf", "Untertitel kommen dazu", "fertig"],
    steps: ["Skript", "Stockmaterial · Pexels", "Sprecher", "Untertitel & Musik"],
    download: ".mp4 laden",
    share: "Teilen",
    shareTitle: "Teilen",
    shareSub: "Verbundene Konten",
    yt: ["YouTube Shorts", "ShortPulse"],
    tt: ["TikTok", "ShortPulse"],
    descLabel: "Beschreibung",
    desc: "Warum ist das Meer salzig? #wissen #shorts",
    send: "Senden",
    sending: "wird gesendet…",
    ytDone: "Auf Shorts hochgeladen",
    ttDone: "An Entwürfe gesendet",
    wrong: "falsch?",
    regen: "neu erzeugen",
    libTitle: "Deine Videos",
    libCount: (n: number) => `${n} Projekte`,
    newVideo: "Neues Video",
    filters: ["Alle", "KI-Shorts", "Hochgeladen", "Edits"],
    justNow: "gerade eben · 0:21 · 9:16",
    ago: (d: number) => `vor ${d} Tagen · 0:2${d % 6} · 9:16`,
    libTitles: ["Wenn der Mond verschwände", "Wenn die Erde stillstünde", "Ein Oktopus hat 3 Herzen", "Warum Katzen Kartons lieben", "Woher Träume kommen", "Warum Honig nie verdirbt", "Wie schnell ist Licht", "5 Fakten über Polen", "Dein Gehirn im Schlaf"],
    hook: "Jeder Tropfen Meer trägt Salz.",
    lines: ["Regen schleift langsam die Felsen ab.", "Flüsse tragen die Mineralien ins Meer.", "Die Sonne hebt das Wasser — das Salz bleibt.", "Nach Millionen Jahren ist das Meer salzig."],
    caps: [
      ["JEDER", "TROPFEN", "TRÄGT", "SALZ"],
      ["REGEN", "SCHLEIFT", "FELSEN"],
      ["FLÜSSE", "TRAGEN", "MINERALIEN", "INS", "MEER"],
      ["WASSER", "GEHT,", "SALZ", "BLEIBT"],
      ["UND", "DAS", "MEER", "WIRD", "SALZIG"],
    ],
    hi: [3, 2, 2, 2, 4],
  },
};

const PROMPTS = [
  "waves crashing on a dark rocky shore, overcast, slow motion",
  "rain falling on weathered cliffs, close-up, moody light",
  "aerial river winding through green valley to the sea",
  "sunlight over calm sea, rising heat haze, golden hour",
  "night ocean under the moon, wide, calm and vast",
];

/* ------------------------------------------------------------------ */
/* Timeline                                                            */
/* ------------------------------------------------------------------ */

const W = 1120;
const H = 700;
const B0 = 5600; // project page
const C0 = 23500; // library
export const SHORTPULSE_DEMO_LENGTH = 31100;
const PLAY0 = B0 + 7400;
const SCENE_MS = 1200;

const PATH: [number, number, number][] = [
  [0, 900, 450],
  [500, 900, 450],
  [1400, 650, 254],
  [2300, 650, 254],
  [3000, 420, 495],
  [3200, 420, 495],
  [3700, 518, 557],
  [3900, 518, 557],
  [4800, 1028, 672],
  [5600, 1028, 672],
  [6600, 960, 560],
  [18400, 966, 554],
  [19000, 1011, 603],
  [20600, 1011, 603],
  [21100, 1020, 511],
  [22700, 1020, 511],
  [23400, 80, 122],
  [24100, 80, 122],
  [25100, 295, 316],
];
const CLICKS = [1450, 3050, 3750, 4850, 19050, 21150, 23450];

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const prog = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
const inOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const out = (x: number) => 1 - Math.pow(1 - x, 3);
const back = (x: number) => {
  const c1 = 1.7;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
};
const lerp = (a: number, b: number, x: number) => a + (b - a) * x;
const typed = (str: string, t: number, a: number, b: number) => str.slice(0, Math.round(str.length * prog(t, a, b)));
const showHide = (t: number, a: number, b: number, fade = 250) => Math.min(prog(t, a, a + fade), 1 - prog(t, b - fade, b));

function cursorAt(t: number) {
  if (t <= PATH[0][0]) return { x: PATH[0][1], y: PATH[0][2] };
  for (let i = 0; i < PATH.length - 1; i++) {
    const [t0, x0, y0] = PATH[i];
    const [t1, x1, y1] = PATH[i + 1];
    if (t >= t0 && t < t1) {
      const e = inOut(prog(t, t0, t1));
      return { x: lerp(x0, x1, e), y: lerp(y0, y1, e) };
    }
  }
  const l = PATH[PATH.length - 1];
  return { x: l[1], y: l[2] };
}

/* ------------------------------------------------------------------ */
/* Icons                                                               */
/* ------------------------------------------------------------------ */

const PATHS: Record<string, ReactNode> = {
  pulse: <path d="M2 12h4l2.5-6 4 13 3-9 1.5 2H22" />,
  wand: <path d="m15 4 1.5 1.5M19.5 8.5 21 10M14 8l-11 11 2 2 11-11zM18 3v2M22 7h-2M20 2l-1 1" />,
  library: (
    <>
      <path d="M4 4v16M8 4v16" />
      <path d="m12 4.5 4 15.5 4-1-4-15.5z" />
    </>
  ),
  folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  share: (
    <>
      <circle cx="18" cy="5" r="2.5" />
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="19" r="2.5" />
      <path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4" />
    </>
  ),
  coins: (
    <>
      <circle cx="9" cy="9" r="6" />
      <path d="M15.5 9.5a6 6 0 1 1-6 6" />
    </>
  ),
  flame: <path d="M12 3c1 4 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-3.5 2-5 1 1 1.5 2 1.5 3 1.5-1.5 2-4.5 1.5-8Z" />,
  trend: <path d="M3 17 9 11l4 4 8-8M15 7h6v6" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />,
  scissors: (
    <>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12" />
    </>
  ),
  doc: <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4" />,
  grid: <path d="M4 9h16M4 15h16M9 4v16M15 4v16" />,
  palette: (
    <>
      <circle cx="13.5" cy="6.5" r="1" fill="currentColor" />
      <circle cx="17.5" cy="10.5" r="1" fill="currentColor" />
      <circle cx="8.5" cy="7.5" r="1" fill="currentColor" />
      <path d="M12 2a10 10 0 0 0 0 20 2 2 0 0 0 2-2c0-1-1-1.6-1-2.6a1.8 1.8 0 0 1 1.8-1.8H17a5 5 0 0 0 5-5c0-4.8-4.5-8.6-10-8.6Z" />
    </>
  ),
  music: (
    <>
      <path d="M9 18V5l12-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="16" r="3" />
    </>
  ),
  chevron: <path d="m9 6 6 6-6 6" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  back: <path d="M19 12H5M11 6l-6 6 6 6" />,
  check: <path d="M20 6 9 17l-5-5" />,
  download: <path d="M12 15V3M7 10l5 5 5-5M5 21h14" />,
  send: <path d="M22 2 11 13M22 2l-7 20-4-9-9-4z" />,
  image: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 17v5" />
    </>
  ),
  type: <path d="M4 7V4h16v3M9 20h6M12 4v16" />,
  thumb: <path d="M7 10v11M15 5.9 14 10h5.8a2 2 0 0 1 2 2.3l-1.4 7A2 2 0 0 1 18.5 21H7V10l4-8a3 3 0 0 1 4 3.9Z" />,
  refresh: <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.3L3 16M3 21v-5h5" />,
  play: <path d="M7 4.5v15a1 1 0 0 0 1.5.9l12-7.5a1 1 0 0 0 0-1.7l-12-7.5A1 1 0 0 0 7 4.5Z" fill="currentColor" />,
  plus: <path d="M12 5v14M5 12h14" />,
  yt: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="4" />
      <path d="m10 9 5 3-5 3z" fill="currentColor" />
    </>
  ),
  tt: <path d="M14 3v11.5a3.5 3.5 0 1 1-3.5-3.5M14 3c.5 2.5 2.5 4.5 5 4.5" />,
};

function Icon({ name, size = 15, style }: { name: keyof typeof PATHS; size?: number; style?: CSSProperties }) {
  return (
    <svg className={s.icon} style={{ width: size, height: size, ...style }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {PATHS[name]}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* Clock                                                               */
/* ------------------------------------------------------------------ */

function useDemoClock(frozen: number | undefined, speed: number, rootRef: React.RefObject<HTMLDivElement | null>) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (frozen !== undefined) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setT(PLAY0 + 300);
      return;
    }
    let visible = true;
    const el = rootRef.current;
    const io = el ? new IntersectionObserver(([e]) => (visible = e.isIntersecting)) : null;
    if (el && io) io.observe(el);
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    const loop = (now: number) => {
      const dt = Math.min(64, now - last);
      last = now;
      if (visible) {
        acc = (acc + dt * speed) % SHORTPULSE_DEMO_LENGTH;
        setT(acc);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      io?.disconnect();
    };
  }, [frozen, speed, rootRef]);
  return frozen ?? t;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

type L = (typeof COPY)["tr"];

export default function ShortPulseDemo({ assets, locale = "en", accent = "rgb(var(--accent))", className, time, speed = 1 }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const t = useDemoClock(time, speed, rootRef);
  const L = (COPY[locale] ?? COPY.en) as L;

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setScale(e.contentRect.width / W));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const loopFade = Math.min(prog(t, 0, 450), 1 - prog(t, SHORTPULSE_DEMO_LENGTH - 600, SHORTPULSE_DEMO_LENGTH));
  const aO = 1 - prog(t, 5300, 5650);
  const bO = prog(t, 5550, 5900) * (1 - prog(t, 23400, 23650));
  const cO = prog(t, 23550, 23900);

  const credits = Math.round(146 - 2 * inOut(prog(t, 4900, 5500)));
  const pillY = lerp(70, 106, out(prog(t, 23450, 23800)));
  const activeNav = t < 23550 ? 0 : 1;
  const header = t < B0 ? L.headers[0] : t < C0 ? L.headers[1] : L.headers[2];

  return (
    <div
      ref={rootRef}
      className={`${s.root} ${className ?? ""}`}
      style={{ "--sp-accent": accent } as CSSProperties}
      role="img"
      aria-label="ShortPulse demo: pick a trending topic, generate a short with script, stock footage, voice and captions, share it to YouTube and TikTok, and find it in your library."
    >
      <div className={s.stage} style={{ transform: `scale(${scale})`, opacity: loopFade }}>
        <div className={s.grid} />
        <div className={s.wash} />

        {aO > 0 && <StudioScene t={t} o={aO} L={L} assets={assets} />}
        {bO > 0 && <ProjectScene t={t} o={bO} L={L} assets={assets} />}
        {cO > 0 && <LibraryScene t={t} o={cO} L={L} assets={assets} />}

        {/* rail */}
        <div className={s.rail}>
          <div className={s.brand}>
            <span className={s.brandMark}>
              <Icon name="pulse" size={16} style={{ strokeWidth: 2.2 }} />
            </span>
            ShortPulse
          </div>
          <div className={s.navPill} style={{ top: pillY }} />
          {(["wand", "library", "folder", "share", "coins"] as const).map((ic, i) => (
            <div key={ic} className={`${s.nav} ${activeNav === i ? s.navOn : ""}`} style={{ top: 70 + i * 36 }}>
              <Icon name={ic} size={15} /> {L.nav[i]}
            </div>
          ))}
          <div className={s.railFoot}>
            {L.nav[4]}
            <b>
              {credits} {L.credits}
            </b>
          </div>
        </div>

        {/* header */}
        <div className={s.header}>
          <div className={`${s.headerLabel} ${s.mono}`}>{header}</div>
          <div className={s.headerCredits}>
            <Icon name="coins" size={13} /> {credits}
          </div>
        </div>

        <Cursor t={t} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Cursor                                                              */
/* ------------------------------------------------------------------ */

function Cursor({ t }: { t: number }) {
  const { x, y } = cursorAt(t);
  const last = [...CLICKS].reverse().find((c) => c <= t);
  const since = last === undefined ? 9999 : t - last;
  const press = since < 160 ? 1 - Math.abs(since - 80) / 80 : 0;
  const ripple = since < 450 ? since / 450 : -1;
  return (
    <>
      {ripple >= 0 && (
        <div className={s.ripple} style={{ left: x - 4 - ripple * 16, top: y - 4 - ripple * 16, width: 8 + ripple * 32, height: 8 + ripple * 32, opacity: 0.9 * (1 - ripple) }} />
      )}
      <svg className={s.cursor} viewBox="0 0 24 24" style={{ transform: `translate(${x - 3}px, ${y - 2}px) scale(${1 - 0.14 * press})`, transformOrigin: "3px 2px" }} aria-hidden>
        <path d="M4 2.5 19.5 11l-6.9 1.9-3.2 6.8z" fill="#fff" stroke="#0a0b0e" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Phone — the vertical short with kinetic captions                     */
/* ------------------------------------------------------------------ */

type CapStyle = 0 | 1 | 2; // classic, highlight, boxed

function Phone({
  x,
  y,
  w,
  h,
  src,
  kb = 0,
  reveal = 1,
  words,
  hi,
  wordIn,
  style,
  progress,
  wave,
  phase = 0,
  radius,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  src?: string;
  kb?: number;
  reveal?: number;
  words?: string[];
  hi?: number;
  wordIn?: (i: number) => number;
  style: CapStyle;
  progress?: number;
  wave?: number;
  phase?: number;
  radius?: number;
}) {
  const fs = w * 0.105;
  return (
    <div className={s.phone} style={{ left: x, top: y, width: w, height: h, borderRadius: radius }}>
      {src && reveal > 0 && (
        <img
          className={s.phoneImg}
          src={src}
          alt=""
          draggable={false}
          style={{ opacity: reveal, filter: `blur(${(1 - reveal) * 14}px)`, transform: `scale(${1.04 + kb * 0.08}) translateY(${-kb * 6}px)` }}
        />
      )}
      {words && (
        <div className={s.capWrap} style={{ fontSize: fs }}>
          {words.map((wd, i) => {
            const k = wordIn ? wordIn(i) : 1;
            if (k <= 0) return null;
            const isHi = i === hi && style !== 0;
            return (
              <span
                key={i}
                className={`${s.capWord} ${isHi && style === 1 ? s.capHi : ""} ${isHi && style === 2 ? s.capBox : ""}`}
                style={{ transform: `scale(${0.6 + 0.4 * back(k)})`, opacity: clamp(k * 2) }}
              >
                {wd}
              </span>
            );
          })}
        </div>
      )}
      {wave !== undefined && wave > 0 && (
        <div className={s.wave} style={{ opacity: wave }}>
          {Array.from({ length: 28 }, (_, i) => (
            <i key={i} style={{ height: `${18 + 82 * Math.abs(Math.sin(i * 0.9 + phase / 110) * Math.sin(i * 0.37 + phase / 290 + 1))}%` }} />
          ))}
        </div>
      )}
      {progress !== undefined && <div className={s.progress} style={{ width: `${progress * 100}%` }} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Scene A — Studio                                                    */
/* ------------------------------------------------------------------ */

function StudioScene({ t, o, L, assets }: { t: number; o: number; L: L; assets: ShortPulseDemoAssets }) {
  const enter = out(prog(t, 80, 520));
  const used = t >= 1450;
  const usePress = t >= 1450 && t < 1600 ? 0.9 : 1;
  const topic = used ? typed(L.topicValue, t, 1500, 2300) : "";
  const focus = t >= 1450 && t < 2900;
  const ring = showHide(t, 1450, 2900, 200);
  const pop = showHide(t, 3080, 4150, 200);
  const style: CapStyle = t >= 3750 ? 1 : 0;
  const swapK = out(prog(t, 3750, 4100));
  const genPress = t >= 4850 && t < 5000 ? 0.94 : 1;
  const rowPressG = t >= 3050 && t < 3200;

  const capWords = L.caps[0];
  const capIn = (i: number) => (t < 3750 ? 1 : prog(t, 3780 + i * 70, 3930 + i * 70));

  return (
    <div className={s.scene} style={{ opacity: o, transform: `translateY(${(1 - enter) * 10}px)` }}>
      <div className={s.h1} style={{ left: 214, top: 64 }}>
        {L.hero[0]}
        <span className={s.accent}>{L.hero[1]}</span>
        {L.hero[2]}
      </div>
      <div className={s.sub} style={{ left: 214, top: 108 }}>
        {L.heroSub}
      </div>
      <div className={s.abs} style={{ left: 214, top: 136, display: "flex", gap: 6 }}>
        {(["wand", "upload", "scissors"] as const).map((ic, i) => (
          <span key={ic} className={`${s.chip} ${i === 0 ? s.chipOn : ""}`} style={{ height: 30 }}>
            <Icon name={ic} size={13} /> {L.modes[i]}
          </span>
        ))}
      </div>

      {/* trends */}
      <div className={s.card} style={{ left: 214, top: 176, width: 476, height: 156 }}>
        <div className={s.abs} style={{ left: 16, top: 12, display: "flex", gap: 8, alignItems: "center", fontWeight: 600, fontSize: 13 }}>
          <Icon name="flame" size={14} style={{ color: "var(--sp-accent)" }} /> {L.trend}
        </div>
        <div className={s.abs} style={{ left: 16, top: 40, display: "flex", gap: 8, alignItems: "center", fontSize: 13, fontWeight: 600 }}>
          <span className={s.badge}>
            <Icon name="trend" size={11} /> {L.rising}
          </span>
          {L.trendTitle}
        </div>
        {L.trendItems.map((it, i) => (
          <div key={i}>
            <div className={s.trendRow} style={{ left: 16, top: 70 + i * 28, color: used && i === 0 ? "var(--sp-text)" : undefined }}>
              • {it}
            </div>
            <div
              className={s.useBtn}
              style={{
                left: 412,
                top: 66 + i * 28,
                transform: i === 0 ? `scale(${usePress})` : undefined,
                background: used && i === 0 ? "var(--sp-accent)" : undefined,
                color: used && i === 0 ? "#0d0b14" : undefined,
                borderColor: used && i === 0 ? "transparent" : undefined,
              }}
            >
              {used && i === 0 ? <Icon name="check" size={12} style={{ strokeWidth: 2.6 }} /> : L.use}
            </div>
          </div>
        ))}
      </div>

      {/* idea */}
      <div className={s.card} style={{ left: 214, top: 346, width: 476, height: 206 }}>
        <div className={s.abs} style={{ left: 16, top: 12, display: "flex", gap: 8, alignItems: "center", fontWeight: 600 }}>
          <Icon name="doc" size={14} /> {L.idea}
        </div>
      </div>
      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 378 }}>
        {L.topic}
      </div>
      <div
        className={s.input}
        style={{
          left: 230,
          top: 398,
          width: 444,
          height: 34,
          borderColor: ring > 0 ? `color-mix(in srgb, var(--sp-accent) ${Math.round(ring * 100)}%, rgba(255,255,255,0.13))` : undefined,
          boxShadow: ring > 0 ? `0 0 0 ${3 * ring}px color-mix(in srgb, var(--sp-accent) 20%, transparent)` : undefined,
        }}
      >
        {topic ? topic : <span className={s.placeholder}>{L.topicPh}</span>}
        {focus && Math.floor(t / 450) % 2 === 0 && <span className={s.caret} />}
      </div>
      {(["grid", "palette", "music"] as const).map((ic, i) => (
        <div
          key={ic}
          className={s.setRow}
          style={{ left: 230, top: 444 + i * 36, width: 444, height: 30, background: i === 1 && (pop > 0 || rowPressG) ? "rgba(255,255,255,0.06)" : undefined }}
        >
          <Icon name={ic} size={14} style={{ color: "var(--sp-muted)" }} />
          {L.rows[i]}
          <small>{L.rowVals[i].replace("{s}", L.styles[style].toLowerCase())}</small>
          <Icon name="chevron" size={13} style={{ color: "var(--sp-faint)", marginLeft: 0 }} />
        </div>
      ))}

      {/* caption style popover */}
      {pop > 0 && (
        <div className={s.popover} style={{ left: 360, top: 516, width: 312, height: 82, opacity: pop, transform: `translateY(${(1 - pop) * -6}px)` }}>
          {L.styles.map((name, i) => (
            <div key={i} className={`${s.swatch} ${style === i ? s.swatchOn : ""}`} style={{ left: 12 + i * 100, top: 8, width: 92, height: 66 }}>
              <span style={{ fontWeight: 800, fontSize: 13, color: "#fff", textShadow: "0 1px 0 #000" }}>
                {i === 0 && "AA BB"}
                {i === 1 && (
                  <>
                    AA <span style={{ color: "var(--sp-cap)" }}>BB</span>
                  </>
                )}
                {i === 2 && (
                  <>
                    AA <span style={{ background: "rgba(0,0,0,.8)", padding: "0 3px", borderRadius: 3 }}>BB</span>
                  </>
                )}
              </span>
              {name}
            </div>
          ))}
        </div>
      )}

      {/* preview + this render */}
      <div className={s.card} style={{ left: 710, top: 176, width: 386, height: 456 }} />
      <Phone x={822} y={190} w={162} h={288} src={assets.scenes[0]} words={capWords} hi={L.hi[0]} wordIn={capIn} style={style} radius={12} />
      {swapK > 0 && swapK < 1 && (
        <div className={s.abs} style={{ left: 822, top: 190, width: 162, height: 288, borderRadius: 12, boxShadow: `0 0 0 ${2 + 6 * (1 - swapK)}px color-mix(in srgb, var(--sp-accent) ${Math.round((1 - swapK) * 60)}%, transparent)` }} />
      )}
      <div className={`${s.abs} ${s.mono}`} style={{ left: 710, width: 386, top: 486, textAlign: "center", fontSize: 10.5, color: "var(--sp-faint)" }}>
        {L.preview}
      </div>
      <div className={s.abs} style={{ left: 730, top: 512, fontWeight: 600, borderLeft: "2px solid var(--sp-accent)", paddingLeft: 8, lineHeight: 1 }}>
        {L.thisRender}
      </div>
      {L.kv.map(([k, v], i) => (
        <div key={k} className={s.kv} style={{ left: 730, width: 346, top: 534 + i * 22 }}>
          {k}
          <b>{v}</b>
        </div>
      ))}

      {/* bottom bar */}
      <div className={s.bottomBar}>
        <div className={s.abs} style={{ left: 24, top: 19, display: "flex", gap: 6, alignItems: "center", color: "var(--sp-muted)", fontSize: 12.5 }}>
          <Icon name="coins" size={13} /> <b style={{ color: "var(--sp-text)", fontWeight: 500 }}>{L.cost}</b> · 146 {L.left}
        </div>
      </div>
      <div className={`${s.btn} ${s.btnAccent}`} style={{ left: 950, top: 655, width: 146, transform: `scale(${genPress})` }}>
        {L.generate} <Icon name="arrow" size={14} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Scene B — Project: render, play, share                               */
/* ------------------------------------------------------------------ */

function ProjectScene({ t, o, L, assets }: { t: number; o: number; L: L; assets: ShortPulseDemoAssets }) {
  const b = t - B0;
  const enter = out(prog(b, 0, 400));

  // pipeline
  const stepDone = [2600, 4600, 6200, 7200];
  const stepStart = [0, 2600, 4600, 6200];
  const statusIdx = b < 2600 ? 0 : b < 4600 ? 1 : b < 6200 ? 2 : b < 7200 ? 3 : 4;
  const ready = b >= 7200;

  // playback
  const p = b - 7400;
  const playing = p >= 0 && p < 5 * SCENE_MS;
  const sceneIdx = playing ? Math.floor(p / SCENE_MS) : p >= 5 * SCENE_MS ? 4 : 0;
  const sceneLocal = playing ? (p % SCENE_MS) / SCENE_MS : p >= 5 * SCENE_MS ? 1 : 0;

  const firstReveal = inOut(prog(b, 2900, 3500));
  const words = b >= 6200 ? L.caps[sceneIdx] : undefined;
  const wordIn = (i: number) => {
    if (!playing && b < 7400) return prog(b, 6300 + i * 120, 6460 + i * 120);
    if (!playing) return 1;
    const n = L.caps[sceneIdx].length;
    const wt = sceneIdx * SCENE_MS + 60 + i * (760 / n);
    return prog(p, wt, wt + 160);
  };
  const waveO = showHide(b, 4600, 6400, 250);

  // share sheet
  const sheet = showHide(b, 13500, 17500, 250);
  const sharePress = b >= 13450 && b < 13600 ? 0.94 : 1;
  const desc = typed(L.desc, b, 13900, 15000);
  const sendPress = b >= 15550 && b < 15700 ? 0.94 : 1;
  const ytP = prog(b, 15600, 16800);
  const ttP = prog(b, 15700, 16400);

  const rowTop = (i: number) => (i === 0 ? 150 : 196 + (i - 1) * 104);
  const rowH = (i: number) => (i === 0 ? 40 : 96);

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

      {/* breakdown */}
      <div className={s.card} style={{ left: 214, top: 134, width: 546, height: 506 }} />
      {[0, 1, 2, 3, 4].map((i) => {
        const appear = out(prog(b, i === 0 ? 400 : 1000 + (i - 1) * 350, (i === 0 ? 400 : 1000 + (i - 1) * 350) + 300));
        if (appear <= 0) return null;
        const text = i === 0 ? typed(L.hook, b, 400, 1000) : typed(L.lines[i - 1], b, 1000 + (i - 1) * 350, 1500 + (i - 1) * 350);
        const top = rowTop(i);
        const on = (playing || (b >= 7400 && p < 5 * SCENE_MS + 600)) && sceneIdx === i;
        const thumbR = inOut(prog(b, 2900 + i * 400, 3300 + i * 400));
        return (
          <div key={i} className={`${s.row} ${on ? s.rowOn : ""}`} style={{ top, height: rowH(i), opacity: appear }}>
            {on && <div className={s.rowBar} />}
            {i === 0 ? (
              <div className={`${s.tc} ${s.mono}`} style={{ left: 18, top: 12, letterSpacing: "0.15em" }}>
                HOOK
              </div>
            ) : (
              <div className={`${s.tc} ${s.mono} ${on ? "" : s.tcDim}`} style={{ left: 18, top: 12 }}>
                0:{String((i - 1) * 4 + 4).padStart(2, "0")}
              </div>
            )}
            <div className={s.line} style={{ left: 76, top: 10 }}>
              {text}
            </div>
            {i > 0 && (
              <>
                <div className={`${s.prompt} ${s.mono}`} style={{ left: 76, top: 34, opacity: prog(b, 1300 + (i - 1) * 350, 1600 + (i - 1) * 350) }}>
                  {PROMPTS[i]}
                </div>
                <div className={`${s.dur} ${s.mono}`} style={{ left: 500, top: 12 }}>
                  4.0s
                </div>
                <div className={s.mini} style={{ left: 76, top: 60, opacity: prog(b, 1500 + (i - 1) * 350, 1800 + (i - 1) * 350) }}>
                  <Icon name="thumb" size={11} /> {L.wrong}
                </div>
                <div className={s.mini} style={{ left: 76 + (L.wrong.length * 6 + 46), top: 60, opacity: prog(b, 1500 + (i - 1) * 350, 1800 + (i - 1) * 350) }}>
                  <Icon name="refresh" size={11} /> {L.regen}
                </div>
                {thumbR > 0 && (
                  <div className={s.thumb} style={{ left: 456, top: 34, width: 72, height: 50, opacity: thumbR }}>
                    <img src={assets.scenes[i]} alt="" style={{ filter: `blur(${(1 - thumbR) * 8}px)` }} />
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}

      {/* output */}
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
        src={firstReveal > 0 ? assets.scenes[sceneIdx] : undefined}
        reveal={sceneIdx === 0 ? firstReveal : 1}
        kb={playing ? sceneLocal : 0}
        words={words}
        hi={L.hi[sceneIdx]}
        wordIn={wordIn}
        style={1}
        wave={waveO}
        phase={b}
        progress={b >= 7400 ? clamp(p / (5 * SCENE_MS)) : undefined}
      />
      {b < 2900 && (
        <div className={`${s.abs} ${s.mono}`} style={{ left: 839, top: 270, width: 198, textAlign: "center", fontSize: 11, color: "var(--sp-faint)" }}>
          <span className={s.spinner} style={{ display: "inline-block", verticalAlign: -3, marginRight: 6 }} />
          {L.statuses[0]}…
        </div>
      )}
      {(["doc", "image", "mic", "type"] as const).map((ic, i) => {
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
      <div className={`${s.btn} ${s.btnAccent}`} style={{ left: 944, top: 586, width: 134, opacity: ready ? 1 : 0.4, transform: `scale(${sharePress})` }}>
        <Icon name="send" size={13} /> {L.share}
      </div>

      {/* share sheet */}
      {sheet > 0 && (
        <div className={s.sheet} style={{ left: 780, top: 260, width: 316, height: 318, opacity: sheet, transform: `translateY(${(1 - sheet) * 10}px) scale(${0.98 + 0.02 * sheet})` }}>
          <div className={s.abs} style={{ left: 14, top: 12, fontWeight: 600, fontSize: 14 }}>
            {L.shareTitle}
          </div>
          <div className={s.abs} style={{ left: 14, top: 32, fontSize: 11, color: "var(--sp-faint)" }}>
            {L.shareSub}
          </div>
          {[
            { icon: "yt" as const, bg: "#ff3b30", name: L.yt, p: ytP, doneTxt: L.ytDone },
            { icon: "tt" as const, bg: "#111", name: L.tt, p: ttP, doneTxt: L.ttDone },
          ].map((a, i) => (
            <div key={i} className={s.acct} style={{ top: 58 + i * 54 }}>
              <span className={s.acctIcon} style={{ background: a.bg, color: "#fff", border: i === 1 ? "1px solid rgba(255,255,255,.2)" : undefined }}>
                <Icon name={a.icon} size={15} />
              </span>
              <span className={s.acctText}>
                {a.name[0]}
                <span>{a.p > 0 && a.p < 1 ? L.sending : a.name[1]}</span>
              </span>
              {a.p >= 1 ? (
                <span className={s.done} style={{ opacity: out(prog(b, i === 0 ? 16800 : 16400, (i === 0 ? 16800 : 16400) + 250)) }}>
                  <Icon name="check" size={12} style={{ strokeWidth: 2.6 }} /> {a.doneTxt}
                </span>
              ) : (
                <span className={s.check}>
                  <Icon name="check" size={11} style={{ strokeWidth: 3 }} />
                </span>
              )}
              {a.p > 0 && a.p < 1 && <span className={s.acctFill} style={{ width: `${a.p * 100}%` }} />}
            </div>
          ))}
          <div className={s.abs} style={{ left: 14, top: 172, fontSize: 11.5, color: "var(--sp-muted)" }}>
            {L.descLabel}
          </div>
          <div className={s.input} style={{ left: 14, top: 192, width: 288, height: 34, fontSize: 12.5 }}>
            {desc}
            {b >= 13900 && b < 15000 && Math.floor(b / 450) % 2 === 0 && <span className={s.caret} />}
          </div>
          <div className={`${s.btn} ${s.btnAccent}`} style={{ left: 178, top: 234, width: 124, transform: `scale(${sendPress})` }}>
            <Icon name="send" size={13} /> {L.send}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Scene C — Library                                                   */
/* ------------------------------------------------------------------ */

const CW = 162;
const TH = 288;
const slot = (i: number) => ({ x: 214 + (i % 5) * 174, y: 172 + Math.floor(i / 5) * 352 });

function LibraryScene({ t, o, L, assets }: { t: number; o: number; L: L; assets: ShortPulseDemoAssets }) {
  const c = t - C0;
  const enter = out(prog(c, 0, 400));
  const lib = assets.library?.length
    ? assets.library
    : assets.scenes.map((src, i) => ({ src, title: L.libTitles[i] }));
  const inserted = c >= 500;
  const newIn = back(prog(c, 900, 1350));
  const hover = c >= 1700 ? out(prog(c, 1700, 1950)) : 0;
  const hp = c - 2100;
  const hIdx = hp > 0 ? Math.floor(hp / SCENE_MS) % 5 : 0;
  const hLocal = hp > 0 ? (hp % SCENE_MS) / SCENE_MS : 0;
  const count = inserted ? 96 : 95;

  return (
    <div className={s.scene} style={{ opacity: o, transform: `translateY(${(1 - enter) * 10}px)` }}>
      <div className={s.h1} style={{ left: 214, top: 60, fontSize: 28 }}>
        {L.libTitle}
      </div>
      <div className={s.sub} style={{ left: 214, top: 100, fontSize: 12 }}>
        {L.libCount(count)}
      </div>
      <div className={`${s.btn} ${s.btnAccent}`} style={{ left: 976, top: 66, width: 120 }}>
        <Icon name="plus" size={14} /> {L.newVideo}
      </div>
      <div className={s.abs} style={{ left: 214, top: 128, display: "flex", gap: 6 }}>
        {L.filters.map((f, i) => (
          <span key={f} className={`${s.chip} ${i === 0 ? s.chipOn : ""}`} style={{ borderColor: i === 0 ? "var(--sp-accent)" : undefined }}>
            {f}
            <span style={{ color: "var(--sp-faint)" }}>{[count, 22, 34, 40][i]}</span>
          </span>
        ))}
      </div>

      {/* existing cards shift one slot to make room */}
      {Array.from({ length: 9 }, (_, i) => {
        const from = slot(i);
        const to = slot(i + 1);
        const k = inOut(prog(c, 500 + i * 35, 950 + i * 35));
        const x = lerp(from.x, to.x, k);
        const y = lerp(from.y, to.y, k);
        return (
          <div key={i} className={s.libCard} style={{ left: x, top: y, width: CW, height: TH + 44 }}>
            <div className={s.libThumb} style={{ height: TH }}>
              <img src={lib[i % lib.length].src} alt="" />
              <span className={s.play}>
                <Icon name="play" size={10} />
              </span>
            </div>
            <div className={s.libTitle} style={{ top: TH + 8, width: CW }}>
              {lib[i % lib.length].title}
            </div>
            <div className={`${s.libMeta} ${s.mono}`} style={{ top: TH + 26 }}>
              {L.ago(i + 2)}
            </div>
          </div>
        );
      })}

      {/* the new one */}
      {newIn > 0 && (
        <div className={s.libCard} style={{ left: 214, top: 172 - hover * 3, width: CW, height: TH + 44, transform: `scale(${0.85 + 0.15 * newIn})`, opacity: clamp(newIn * 1.5), zIndex: 3 }}>
          <div className={s.libThumb} style={{ height: TH, borderColor: "var(--sp-accent)", boxShadow: `0 0 0 ${3 * (1 - prog(c, 1350, 2600))}px color-mix(in srgb, var(--sp-accent) 35%, transparent), 0 20px 40px -18px rgba(0,0,0,.9)` }}>
            <Phone
              x={0}
              y={0}
              w={CW}
              h={TH}
              radius={0}
              src={assets.scenes[hIdx]}
              kb={hp > 0 ? hLocal : 0}
              words={L.caps[hIdx]}
              hi={L.hi[hIdx]}
              style={1}
              wordIn={(i) => (hp > 0 ? prog(hLocal * SCENE_MS, 60 + i * (760 / L.caps[hIdx].length), 220 + i * (760 / L.caps[hIdx].length)) : 1)}
            />
            <div className={s.plat}>
              <span>
                <Icon name="yt" size={11} /> ✓
              </span>
              <span>
                <Icon name="tt" size={11} /> ✓
              </span>
            </div>
            {hover < 0.5 && (
              <span className={s.play}>
                <Icon name="play" size={10} />
              </span>
            )}
          </div>
          <div className={s.libTitle} style={{ top: TH + 8, width: CW }}>
            {L.topicValue.split("?")[0] + "?"}
          </div>
          <div className={`${s.libMeta} ${s.mono}`} style={{ top: TH + 26, color: "var(--sp-accent)" }}>
            {L.justNow}
          </div>
        </div>
      )}
    </div>
  );
}
