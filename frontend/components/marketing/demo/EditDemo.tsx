"use client";

/* eslint-disable @next/next/no-img-element */
import { memo, useRef, type CSSProperties } from "react";
import s from "./ShortPulseDemo.module.css";
import {
  Cursor,
  Icon,
  Shell,
  SHELL,
  StudioHead,
  back,
  clamp,
  cursorAt,
  inOut,
  lerp,
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
 * Edit my clips — drop in clips, pick a song and the part of it, choose a
 * look, and it cuts a beat-synced fan edit: build-up, a flash on the drop,
 * zoom hits on every beat, a slow-motion hold.
 *
 * Labels are the studio's own (messages: studio.beat); 15 seconds is
 * 3 credits (BEAT_EDIT_COSTS).
 */

export type EditDemoAssets = {
  /** Six of your own clips' stills (any shape; vertical looks best). */
  clips: [string, string, string, string, string, string];
};

type Props = {
  assets: EditDemoAssets;
  locale?: Locale;
  accent?: string;
  className?: string;
  time?: number;
  speed?: number;
  fadeEdges?: boolean;
};

const COPY = {
  tr: {
    title: ["Kliplerin, ", "ritme göre kesilmiş", "."] as [string, string, string],
    sub: "Kliplerini at, bir şarkı seç — ritmi ve drop'u bulur, hepsini birlikte keser.",
    clips: "Kliplerin",
    drop: "Kliplerini buraya bırak",
    dropHint: "En fazla 12 video — şekli fark etmez, 9:16'ya uyarlanır",
    total: "6 klip · 0:52",
    music: "Müzik",
    part: "Şarkının hangi kısmı",
    style: "Stil",
    styles: ["Enerjik", "Sinematik", "Sakin"],
    look: "Görünüm",
    looks: ["Stile göre", "Canlı", "Sinema", "Altın", "Gece"],
    titleL: "Videodaki başlık",
    titlePh: "örn. BU SEZONUN EN İYİ ÇALIMLARI",
    titleV: "SINIR YOK",
    cost: "3 kredi",
    button: "Edit'i hazırla",
    what: "Ne yapar",
    steps: [
      "Şarkının temposunu, vuruşlarını ve drop'unu bulur.",
      "Her klibi ölçer ve en hareketli anını alır.",
      "Önce yükselir, sonra drop'ta stilin en güçlü efektiyle vurur.",
      "Vuruşta keser, rengi ayarlar, her şeyi 9:16'ya oturtur.",
    ],
    details: ["162 BPM · drop 0:12", "6 klip · en hareketli 1.5s", "flaş + zoom drop'ta", "Gece rengi · 9:16"],
    ready: "Edit hazır · 0:08 · 9:16",
  },
  en: {
    title: ["Your clips, ", "cut to the beat", "."] as [string, string, string],
    sub: "Drop in your clips and pick a song — it finds the beat and the drop and cuts them together.",
    clips: "Your clips",
    drop: "Drop your clips here",
    dropHint: "Up to 12 videos — any shape, they are framed to 9:16",
    total: "6 clips · 0:52",
    music: "Music",
    part: "Which part of the song",
    style: "Style",
    styles: ["Energetic", "Cinematic", "Calm"],
    look: "Look",
    looks: ["Style's own", "Vivid", "Cinema", "Golden", "Night"],
    titleL: "Title on the video",
    titlePh: "e.g. HIS BEST SKILLS THIS SEASON",
    titleV: "NO LIMITS",
    cost: "3 credits",
    button: "Make the edit",
    what: "What it does",
    steps: [
      "Finds the tempo, the beats and the drop in the song.",
      "Measures every clip and takes its most active moment.",
      "Builds up, then hits the drop with the style's biggest effect.",
      "Cuts on the beat, grades the colour, frames everything to 9:16.",
    ],
    details: ["162 BPM · drop at 0:12", "6 clips · best 1.5s each", "flash + zoom on the drop", "Night grade · 9:16"],
    ready: "Edit ready · 0:08 · 9:16",
  },
  pl: {
    title: ["Twoje klipy, ", "cięte do rytmu", "."] as [string, string, string],
    sub: "Wrzuć klipy i wybierz utwór — znajduje rytm i drop, i tnie wszystko razem.",
    clips: "Twoje klipy",
    drop: "Upuść tutaj klipy",
    dropHint: "Do 12 filmów — dowolny kształt, kadrujemy do 9:16",
    total: "6 klipów · 0:52",
    music: "Muzyka",
    part: "Który fragment utworu",
    style: "Styl",
    styles: ["Energiczny", "Filmowy", "Spokojny"],
    look: "Wygląd",
    looks: ["Według stylu", "Żywy", "Kino", "Złoty", "Noc"],
    titleL: "Tytuł na wideo",
    titlePh: "np. NAJLEPSZE DRYBLINGI SEZONU",
    titleV: "BEZ GRANIC",
    cost: "3 kredyty",
    button: "Zrób montaż",
    what: "Co robi",
    steps: [
      "Znajduje tempo, uderzenia i drop w utworze.",
      "Mierzy każdy klip i bierze jego najbardziej dynamiczny moment.",
      "Buduje napięcie, a na dropie uderza najmocniejszym efektem stylu.",
      "Tnie w rytm, koryguje kolory, kadruje wszystko do 9:16.",
    ],
    details: ["162 BPM · drop 0:12", "6 klipów · najlepsze 1,5 s", "błysk + zoom na dropie", "Kolor nocy · 9:16"],
    ready: "Montaż gotowy · 0:08 · 9:16",
  },
  de: {
    title: ["Deine Clips, ", "im Takt geschnitten", "."] as [string, string, string],
    sub: "Clips ablegen, Song wählen — es findet Beat und Drop und schneidet alles zusammen.",
    clips: "Deine Clips",
    drop: "Clips hier ablegen",
    dropHint: "Bis zu 12 Videos — jedes Format, sie werden auf 9:16 gebracht",
    total: "6 Clips · 0:52",
    music: "Musik",
    part: "Welcher Teil des Songs",
    style: "Stil",
    styles: ["Energetisch", "Filmisch", "Ruhig"],
    look: "Look",
    looks: ["Wie der Stil", "Kräftig", "Kino", "Golden", "Nacht"],
    titleL: "Titel im Video",
    titlePh: "z. B. SEINE BESTEN SKILLS DIESER SAISON",
    titleV: "OHNE GRENZEN",
    cost: "3 Credits",
    button: "Edit erstellen",
    what: "Was es macht",
    steps: [
      "Findet Tempo, Beats und den Drop im Song.",
      "Misst jeden Clip und nimmt seinen bewegtesten Moment.",
      "Baut auf und trifft den Drop mit dem stärksten Effekt des Stils.",
      "Schneidet im Takt, gradet die Farben, bringt alles auf 9:16.",
    ],
    details: ["162 BPM · Drop bei 0:12", "6 Clips · je 1,5 s", "Blitz + Zoom am Drop", "Nacht-Look · 9:16"],
    ready: "Edit fertig · 0:08 · 9:16",
  },
};

/* ---------- timeline ---------- */

const GO = 7850; // "make the edit"
const PLAY = 11800;
const BEAT = 370;
const DROP = PLAY + 8 * BEAT;
const END_PLAY = PLAY + 8000;
export const EDIT_DEMO_LENGTH = 21800;

type Cut = { a: number; b: number; clip: number; slow?: boolean };
const CUTS: Cut[] = (() => {
  const out: Cut[] = [];
  let t = PLAY;
  let c = 0;
  while (t < DROP) {
    out.push({ a: t, b: t + 2 * BEAT, clip: c++ % 6 });
    t += 2 * BEAT;
  }
  for (let i = 0; i < 8; i++) {
    out.push({ a: t, b: t + BEAT, clip: c++ % 6 });
    t += BEAT;
  }
  out.push({ a: t, b: t + 4 * BEAT, clip: 2, slow: true });
  t += 4 * BEAT;
  while (t < END_PLAY) {
    out.push({ a: t, b: Math.min(END_PLAY, t + BEAT), clip: c++ % 6 });
    t += BEAT;
  }
  return out;
})();

const PATH: Path = [
  [0, 1000, 250],
  [500, 1000, 250],
  [1400, 452, 254],
  [2300, 452, 254],
  [2900, 268, 409],
  [2950, 268, 409],
  [3800, 362, 409],
  [4300, 362, 409],
  [4900, 623, 543],
  [5300, 623, 543],
  [5900, 452, 602],
  [7100, 452, 602],
  [7800, 1023, 672],
  [8800, 980, 640],
];
const CLICKS = [1450, 2950, 3850, 4950, 5950, 7850];
const HELD: [number, number][] = [
  [500, 1450],
  [2950, 3850],
];

const WAVE = Array.from({ length: 96 }, (_, i) => 0.18 + 0.82 * Math.abs(Math.sin(i * 0.53) * Math.cos(i * 0.21 + 0.6) * (i > 30 && i < 60 ? 1 : 0.55)));
const NIGHT = "brightness(0.82) contrast(1.18) saturate(0.85)";

function EditDemo({ assets, locale = "en", accent = "rgb(var(--accent))", className, time, speed = 1, fadeEdges = true }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const scale = useStageScale(rootRef);
  const t = useDemoClock(time, speed, rootRef, EDIT_DEMO_LENGTH, DROP + 200);
  const L = (COPY[locale] ?? COPY.en) as L;
  const loopFade = fadeEdges ? Math.min(prog(t, 0, 450), 1 - prog(t, EDIT_DEMO_LENGTH - 600, EDIT_DEMO_LENGTH)) : 1;
  const credits = Math.round(146 - 3 * inOut(prog(t, GO + 50, GO + 550)));

  return (
    <div
      ref={rootRef}
      className={`${s.root} ${className ?? ""}`}
      style={{ "--sp-accent": accent } as CSSProperties}
      role="img"
      aria-label="ShortPulse demo: drop in clips, pick a song and a look, and get a beat-synced edit with a flash on the drop."
    >
      <div className={s.stage} style={{ transform: `scale(${scale})`, opacity: loopFade }}>
        <div className={s.grid} />
        <div className={s.wash} />
        <Scene t={t} L={L} assets={assets} locale={locale} />
        <Shell locale={locale} credits={credits} pillY={70} activeNav={0} header={SHELL[locale].headers[0]} />
        <Cursor t={t} path={PATH} clicks={CLICKS} pressed={HELD} />
        {t >= 500 && t < 1450 && <ClipStack t={t} assets={assets} />}
      </div>
    </div>
  );
}

export default memo(EditDemo);

type L = (typeof COPY)["tr"];

function ClipStack({ t, assets }: { t: number; assets: EditDemoAssets }) {
  const { x, y } = cursorAt(PATH, t);
  const o = out(prog(t, 500, 700));
  return (
    <div className={s.abs} style={{ left: x - 24, top: y - 40, zIndex: 30, opacity: o }}>
      {[2, 1, 0].map((i) => (
        <div key={i} className={s.clipThumb} style={{ left: i * 10, top: i * -4, width: 44, height: 72, transform: `rotate(${(i - 1) * 7}deg)`, boxShadow: "0 14px 30px -10px rgba(0,0,0,.9)" }}>
          <img src={assets.clips[i]} alt="" />
        </div>
      ))}
      <span className={s.tick} style={{ position: "absolute", left: 52, top: -12, width: 20, height: 20, fontSize: 10.5, fontWeight: 700 }}>
        6
      </span>
    </div>
  );
}

function Scene({ t, L, assets, locale }: { t: number; L: L; assets: EditDemoAssets; locale: Locale }) {
  const enter = out(prog(t, 80, 520));
  const over = t >= 1000 && t < 1450;
  const dropped = t >= 1450;
  const night = t >= 4950;
  const nightK = out(prog(t, 4950, 5300));

  // song window drag, snapping to a bar at the end
  const dragK = inOut(prog(t, 2950, 3800));
  const snap = t >= 3800 ? 1 + 0.06 * Math.sin(prog(t, 3800, 4000) * Math.PI) * (1 - prog(t, 3800, 4000)) : 1;
  const winX = 236 + 94 * dragK * snap;
  const startSec = Math.round(1 + 4 * dragK);
  const playingPart = t >= 2950 && t < 4300;

  const titleTxt = typed(L.titleV, t, 6000, 7000);
  const titleFocus = t >= 5950 && t < 7400;
  const goPress = t >= GO && t < GO + 150 ? 0.94 : 1;

  // right panel
  const stepsO = 1 - prog(t, 11200, 11600);
  const resultO = out(prog(t, 11400, 11900));
  const ready = showHide(t, END_PLAY + 150, EDIT_DEMO_LENGTH - 200, 300);

  return (
    <div className={s.scene} style={{ opacity: 1, transform: `translateY(${(1 - enter) * 10}px)` }}>
      <StudioHead locale={locale} title={L.title} sub={L.sub} mode={2} />

      {/* form */}
      <div className={s.card} style={{ left: 214, top: 176, width: 476, height: 456 }} />
      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 188 }}>
        {L.clips}
      </div>
      {!dropped ? (
        <div className={`${s.drop} ${over ? s.dropOver : ""}`} style={{ left: 230, top: 208, width: 444, height: 92 }}>
          <Icon name="upload" size={18} style={{ color: over ? "var(--sp-accent)" : "var(--sp-muted)" }} />
          {L.drop}
          <small>{L.dropHint}</small>
        </div>
      ) : (
        <>
          {assets.clips.map((src, i) => {
            const k = back(prog(t, 1450 + i * 90, 1750 + i * 90));
            if (k <= 0) return null;
            return (
              <div key={i} className={s.clipThumb} style={{ left: 232 + i * 60, top: 210, width: 52, height: 86, transform: `scale(${0.7 + 0.3 * k})`, opacity: clamp(k * 1.5) }}>
                <img src={src} alt="" style={{ filter: night ? NIGHT : undefined }} />
                {night && <div className={s.grade} style={{ background: `rgba(60,80,190,${0.35 * nightK})` }} />}
                <b>0:{String(((i * 3) % 9) + 4).padStart(2, "0")}</b>
              </div>
            );
          })}
          <div className={`${s.abs} ${s.mono}`} style={{ left: 600, top: 246, fontSize: 10.5, color: "var(--sp-faint)", opacity: out(prog(t, 2000, 2300)) }}>
            {L.total}
          </div>
        </>
      )}

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 314 }}>
        {L.music}
      </div>
      <div className={s.song} style={{ left: 230, top: 332, width: 444, height: 32 }}>
        {playingPart ? (
          <span className={s.eq}>
            {[0, 1, 2].map((i) => (
              <i key={i} style={{ height: `${30 + 70 * Math.abs(Math.sin(t / 140 + i * 1.3))}%` }} />
            ))}
          </span>
        ) : (
          <Icon name="play" size={12} />
        )}
        Anarchobliss
        <small>upbeat</small>
      </div>

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 374 }}>
        {L.part}
      </div>
      <div className={s.waveform} style={{ left: 230, top: 392, width: 444, height: 34 }}>
        {WAVE.map((h, i) => (
          <i key={i} style={{ height: `${h * 100}%`, background: 230 + 4 + i * 4.6 >= winX && 230 + 4 + i * 4.6 <= winX + 64 ? "var(--sp-accent)" : undefined }} />
        ))}
      </div>
      <div className={s.window} style={{ left: winX, top: 392, width: 64, height: 34 }}>
        <span>DROP</span>
      </div>
      <div className={`${s.abs} ${s.mono}`} style={{ left: 230, top: 432, fontSize: 11, color: "var(--sp-muted)" }}>
        0:{String(startSec).padStart(2, "0")} – 0:{String(startSec + 15).padStart(2, "0")}
        <span style={{ color: "var(--sp-faint)", marginLeft: 8 }}>162 BPM</span>
      </div>

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 456 }}>
        {L.style}
      </div>
      <div className={s.pick} style={{ left: 230, top: 474 }}>
        {(["zap", "film", "music"] as const).map((ic, i) => (
          <span key={ic} className={`${s.chip} ${i === 0 ? s.chipOn : ""}`} style={{ width: 100, borderColor: i === 0 ? "var(--sp-accent)" : undefined }}>
            <Icon name={ic} size={12} /> {L.styles[i]}
          </span>
        ))}
      </div>

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 512 }}>
        {L.look}
      </div>
      <div className={s.pick} style={{ left: 230, top: 530 }}>
        {["#8a8a8a", "#e05a8a", "#5f8f74", "#e0a050", "#3b4f9e"].map((c, i) => {
          const on = night ? i === 4 : i === 0;
          return (
            <span key={c} className={`${s.chip} ${on ? s.chipOn : ""}`} style={{ width: 82, padding: "0 6px", borderColor: on ? "var(--sp-accent)" : undefined, transform: i === 4 && t >= 4950 && t < 5100 ? "scale(.93)" : undefined }}>
              <span className={s.dotSw} style={{ background: c }} />
              {L.looks[i]}
            </span>
          );
        })}
      </div>

      <div className={`${s.label} ${s.abs}`} style={{ left: 230, top: 568 }}>
        {L.titleL}
      </div>
      <div className={s.input} style={{ left: 230, top: 586, width: 444, height: 32, fontSize: 12.5, borderColor: titleFocus ? "var(--sp-accent)" : undefined }}>
        {titleTxt ? titleTxt : <span className={s.placeholder}>{L.titlePh}</span>}
        {titleFocus && Math.floor(t / 450) % 2 === 0 && <span className={s.caret} />}
      </div>

      {/* right panel */}
      <div className={s.card} style={{ left: 710, top: 176, width: 386, height: 456 }} />
      {stepsO > 0 && (
        <div style={{ opacity: stepsO }}>
          <div className={s.abs} style={{ left: 730, top: 192, fontWeight: 600 }}>
            {L.what}
          </div>
          {L.steps.map((txt, i) => {
            const a = GO + 100 + i * 750;
            const done = t >= a + 750;
            const active = t >= a && !done;
            const y = 226 + i * 66;
            return (
              <div key={i}>
                <div className={s.stepNo} style={{ left: 730, top: y + 1 }}>
                  0{i + 1}
                </div>
                <div className={s.stepTxt} style={{ left: 760, top: y - 1, width: 290, color: done ? "var(--sp-text)" : undefined }}>
                  {txt}
                </div>
                {done && (
                  <div className={s.stepDetail} style={{ left: 760, top: y + 40, opacity: out(prog(t, a + 750, a + 1000)) }}>
                    {L.details[i]}
                  </div>
                )}
                <span className={s.abs} style={{ left: 1060, top: y + 2 }}>
                  {done ? (
                    <span className={s.tick} style={{ transform: `scale(${back(prog(t, a + 750, a + 1000))})` }}>
                      <Icon name="check" size={10} style={{ strokeWidth: 3 }} />
                    </span>
                  ) : active ? (
                    <span className={s.spinner} style={{ display: "block" }} />
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {resultO > 0 && <Result t={t} o={resultO} L={L} assets={assets} />}
      {ready > 0 && (
        <div className={s.toastSp} style={{ right: 24, top: 58, opacity: ready, transform: `translateY(${(1 - ready) * -8}px)` }}>
          <span className={s.tick} style={{ width: 22, height: 22 }}>
            <Icon name="check" size={12} style={{ strokeWidth: 3 }} />
          </span>
          {L.ready}
        </div>
      )}

      <div className={s.bottomBar}>
        <div className={s.abs} style={{ left: 24, top: 19, display: "flex", gap: 6, alignItems: "center", color: "var(--sp-muted)", fontSize: 12.5 }}>
          <Icon name="coins" size={13} /> <b style={{ color: "var(--sp-text)", fontWeight: 500 }}>{L.cost}</b> · 146 {SHELL[locale].left}
        </div>
      </div>
      <div className={`${s.btn} ${s.btnAccent}`} style={{ left: 950, top: 655, width: 146, opacity: dropped ? 1 : 0.45, transform: `scale(${goPress})` }}>
        <Icon name="scissors" size={14} /> {L.button}
      </div>
    </div>
  );
}

function Result({ t, o, L, assets }: { t: number; o: number; L: L; assets: EditDemoAssets }) {
  const playing = t >= PLAY && t < END_PLAY;
  const tt = clamp(t, PLAY, END_PLAY - 1);
  const cut = CUTS.find((c) => tt >= c.a && tt < c.b) ?? CUTS[CUTS.length - 1];
  const local = (tt - cut.a) / (cut.b - cut.a);

  // zoom hit on each beat after the drop, softer cut-punch before it
  let punch = 0;
  if (tt >= DROP) {
    const lastBeat = DROP + Math.floor((tt - DROP) / BEAT) * BEAT;
    punch = 0.09 * Math.exp(-(tt - lastBeat) / 110);
  } else {
    punch = 0.04 * Math.exp(-(tt - cut.a) / 140);
  }
  const zoom = cut.slow ? 1.04 + 0.1 * local : 1.04 + punch + 0.03 * local;
  const shake = tt >= DROP ? Math.sin(tt * 0.09) * 6 * Math.exp(-(tt - DROP) / 220) : 0;
  const flash = tt >= DROP ? Math.exp(-(tt - DROP) / 90) : 0;
  const words = L.titleV.split(" ");
  const titleO = 1 - prog(t, 14000, 14400);

  const mtX = 730;
  const mtW = 346;
  const px = (ms: number) => mtX + ((ms - PLAY) / (END_PLAY - PLAY)) * mtW;

  return (
    <div style={{ opacity: o }}>
      <div className={s.phone} style={{ left: 813, top: 192, width: 180, height: 320, transform: `scale(${0.96 + 0.04 * o})` }}>
        <img
          className={s.phoneImg}
          src={assets.clips[cut.clip]}
          alt=""
          style={{ transform: `translateX(${shake}px) scale(${zoom})`, filter: NIGHT + (cut.slow ? " blur(0.3px)" : "") }}
        />
        <div className={s.grade} style={{ background: "rgba(55,75,200,0.5)" }} />
        {titleO > 0 && (
          <div className={s.titleOver} style={{ fontSize: 19, opacity: titleO }}>
            {words.map((w, i) => {
              const k = prog(t, PLAY + 100 + i * 260, PLAY + 260 + i * 260);
              return k > 0 ? (
                <span key={i} style={{ display: "inline-block", marginRight: 5, transform: `translateY(${(1 - out(k)) * 6}px)`, opacity: k }}>
                  {w}
                </span>
              ) : null;
            })}
          </div>
        )}
        {cut.slow && playing && (
          <div className={`${s.abs} ${s.mono}`} style={{ right: 8, top: 8, fontSize: 9.5, padding: "2px 6px", borderRadius: 5, background: "rgba(0,0,0,.55)", zIndex: 2 }}>
            0.5×
          </div>
        )}
        {flash > 0.01 && <div className={s.flash} style={{ opacity: flash }} />}
        <div className={s.progress} style={{ width: `${prog(t, PLAY, END_PLAY) * 100}%`, zIndex: 2 }} />
      </div>

      {/* mini timeline */}
      <div className={s.mt} style={{ left: mtX, top: 536, width: mtW, height: 44 }}>
        {CUTS.map((c, i) => (
          <div key={i} className={s.seg} style={{ left: px(c.a) - mtX, width: px(c.b) - px(c.a) }}>
            <img src={assets.clips[c.clip]} alt="" style={{ filter: NIGHT }} />
          </div>
        ))}
        {Array.from({ length: Math.floor((END_PLAY - PLAY) / BEAT) + 1 }, (_, i) => (
          <div key={i} className={s.beatTick} style={{ left: px(PLAY + i * BEAT) - mtX }} />
        ))}
        <div className={s.dropMark} style={{ left: px(DROP) - mtX - 1 }}>
          DROP
        </div>
      </div>
      <div className={s.playhead} style={{ left: lerp(mtX, mtX + mtW, prog(t, PLAY, END_PLAY)) - 1, top: 530, height: 56, zIndex: 4 }} />
      <div className={`${s.abs} ${s.mono}`} style={{ left: mtX, top: 590, width: mtW, display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--sp-faint)" }}>
        <span>0:00</span>
        <span>162 BPM</span>
        <span>0:08</span>
      </div>
    </div>
  );
}
