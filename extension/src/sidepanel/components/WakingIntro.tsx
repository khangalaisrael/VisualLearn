/**
 * Shown while the free-tier server wakes up (30-60 s): instead of a bare
 * "please wait", a short looping intro to what VisionLearn does, in the
 * brand's colours (the logo's deep indigo, lavender capture corners and
 * amber V). Pure SVG + CSS (index.css, `vl-` classes): a few KB, no video.
 *
 * Motion follows the UI guide: fades and short slides only, nothing that
 * bounces. With reduced motion turned on, index.css cuts every animation
 * to its end state, so each scene simply appears.
 */

import { useEffect, useState, type CSSProperties } from "react";

import { warmUpSeconds } from "../../shared/api-client";

const INDIGO = "#2e2a8a";
const LAVENDER = "#c7d2fe";
const AMBER = "#fcd34d";
const PAPER = "#f8fafc";
const INK = "#94a3b8";

const SCENE_MS = 5200;
const EXPECTED_WAKE_S = 60;

/** Animation delay, as a CSS variable the vl- classes read. */
const at = (ms: number): CSSProperties => ({ ["--d" as string]: `${ms}ms` });

function Corners({ x, y, w, h, delay = 0 }: { x: number; y: number; w: number; h: number; delay?: number }) {
  const s = Math.min(w, h) * 0.18;
  const paths = [
    `M${x} ${y + s}V${y}h${s}`,
    `M${x + w - s} ${y}h${s}v${s}`,
    `M${x + w} ${y + h - s}v${s}h${-s}`,
    `M${x + s} ${y + h}h${-s}v${-s}`,
  ];
  return (
    <g fill="none" stroke={LAVENDER} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
      {paths.map((d, i) => (
        <path key={i} d={d} className="vl-draw" pathLength={1} style={at(delay + i * 90)} />
      ))}
    </g>
  );
}

/** A small slide: title bar and a few lines of text. */
function Slide({ children }: { children?: React.ReactNode }) {
  return (
    <g className="vl-rise" style={at(0)}>
      <rect x={70} y={34} width={180} height={112} rx={8} fill={PAPER} />
      <rect x={84} y={48} width={84} height={9} rx={3} fill={INDIGO} />
      <rect x={84} y={66} width={120} height={5} rx={2.5} fill={INK} />
      <rect x={84} y={77} width={96} height={5} rx={2.5} fill={INK} />
      {children}
    </g>
  );
}

function LogoScene() {
  return (
    <g>
      <g transform="translate(112 42) scale(1)">
        <rect width={96} height={96} rx={22} fill="#3b36a8" className="vl-fade" style={at(0)} />
        <Corners x={18} y={22} w={60} h={52} delay={150} />
        <path
          d="M30 34l18 32 18-32"
          fill="none"
          stroke={AMBER}
          strokeWidth={9}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="vl-draw"
          pathLength={1}
          style={at(650)}
        />
      </g>
      <text x={160} y={166} textAnchor="middle" fill="white" fontSize={20} fontWeight={600} className="vl-rise" style={at(1100)}>
        VisionLearn
      </text>
    </g>
  );
}

function CaptureScene() {
  return (
    <g>
      <Slide>
        <rect x={84} y={92} width={60} height={40} rx={4} fill={LAVENDER} opacity={0.7} />
        <rect x={152} y={96} width={84} height={5} rx={2.5} fill={INK} />
        <rect x={152} y={107} width={70} height={5} rx={2.5} fill={INK} />
      </Slide>
      <Corners x={58} y={24} w={204} h={132} delay={500} />
      <rect x={66} y={34} width={188} height={3} rx={1.5} fill={AMBER} className="vl-scan" style={at(1100)} />
    </g>
  );
}

function ReadScene() {
  return (
    <g>
      <Slide>
        <text x={86} y={104} fontSize={11} fontStyle="italic" fill={INDIGO} fontFamily="serif">
          T(n) = 2T(n/2) + n
        </text>
        <rect x={84} y={116} width={68} height={22} rx={3} fill="#1e1b4b" />
        <rect x={89} y={122} width={40} height={3} rx={1.5} fill={AMBER} />
        <rect x={89} y={130} width={28} height={3} rx={1.5} fill={LAVENDER} />
        <g stroke={INDIGO} strokeWidth={1.5} fill={PAPER}>
          <line x1={224} y1={108} x2={211} y2={127} />
          <line x1={224} y1={108} x2={237} y2={127} />
          <circle cx={224} cy={106} r={6} />
          <circle cx={211} cy={129} r={6} />
          <circle cx={237} cy={129} r={6} />
        </g>
      </Slide>
      {[
        { x: 80, y: 92, w: 114, h: 17, d: 500 },
        { x: 80, y: 113, w: 76, h: 28, d: 1200 },
        { x: 201, y: 96, w: 46, h: 43, d: 1900 },
      ].map((box) => (
        <rect
          key={box.d}
          x={box.x}
          y={box.y}
          width={box.w}
          height={box.h}
          rx={4}
          fill="none"
          stroke={AMBER}
          strokeWidth={2.5}
          className="vl-draw"
          pathLength={1}
          style={at(box.d)}
        />
      ))}
    </g>
  );
}

function AskScene() {
  return (
    <g>
      <g className="vl-rise" style={at(100)}>
        <rect x={136} y={36} width={146} height={30} rx={12} fill={LAVENDER} />
        <text x={150} y={56} fontSize={12} fill={INDIGO}>
          Why is it n log n?
        </text>
      </g>
      <g className="vl-rise" style={at(900)}>
        <rect x={38} y={78} width={196} height={66} rx={12} fill={PAPER} />
        <rect x={52} y={92} width={150} height={6} rx={3} fill={INK} />
        <rect x={52} y={105} width={168} height={6} rx={3} fill={INK} />
        <rect x={52} y={118} width={120} height={6} rx={3} fill={INK} />
        <rect x={52} y={130} width={60} height={6} rx={3} fill={AMBER} className="vl-fade" style={at(1500)} />
      </g>
      <g className="vl-rise" style={at(1900)}>
        <rect x={38} y={152} width={92} height={22} rx={11} fill="none" stroke={LAVENDER} strokeWidth={1.5} />
        <text x={50} y={167} fontSize={10.5} fill={LAVENDER}>
          Give an example
        </text>
      </g>
    </g>
  );
}

function StudyScene() {
  const cards = [
    { x: 46, label: "Recent", d: 100 },
    { x: 132, label: "Notes", d: 500 },
    { x: 218, label: "Quiz", d: 900 },
  ];
  return (
    <g>
      {cards.map((card) => (
        <g key={card.label} className="vl-rise" style={at(card.d)}>
          <rect x={card.x} y={48} width={66} height={86} rx={10} fill={PAPER} />
          <rect x={card.x + 10} y={60} width={46} height={28} rx={4} fill={LAVENDER} />
          <rect x={card.x + 10} y={96} width={40} height={5} rx={2.5} fill={INK} />
          <rect x={card.x + 10} y={106} width={30} height={5} rx={2.5} fill={INK} />
          <text x={card.x + 33} y={152} textAnchor="middle" fontSize={11} fill="white">
            {card.label}
          </text>
        </g>
      ))}
      <path
        d="M233 118l7 7 13-15"
        fill="none"
        stroke={AMBER}
        strokeWidth={4}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="vl-draw"
        pathLength={1}
        style={at(1500)}
      />
    </g>
  );
}

const SCENES: { caption: string; Scene: () => JSX.Element }[] = [
  { caption: "Understand any lecture slide", Scene: LogoScene },
  { caption: "Capture the slide you're looking at", Scene: CaptureScene },
  { caption: "It reads the equations, code and diagrams", Scene: ReadScene },
  { caption: "Ask anything about it, in plain words", Scene: AskScene },
  { caption: "Come back to it later, with notes and quizzes", Scene: StudyScene },
];

export function WakingIntro(): JSX.Element {
  const [scene, setScene] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    // The server began waking when the panel opened, not when this appeared,
    // so the bar starts from there.
    const started = Date.now() - warmUpSeconds() * 1000;
    const sceneTimer = setInterval(() => setScene((current) => (current + 1) % SCENES.length), SCENE_MS);
    const clock = setInterval(() => setElapsed((Date.now() - started) / 1000), 500);
    return () => {
      clearInterval(sceneTimer);
      clearInterval(clock);
    };
  }, []);

  // Fills over the usual wake time, then waits just short of the end.
  return <IntroFrame scene={scene} progress={Math.min(0.95, elapsed / EXPECTED_WAKE_S)} />;
}

/** One moment of the intro: which scene, and how far the bar has filled (0-1). */
export function IntroFrame({ scene, progress }: { scene: number; progress: number }): JSX.Element {
  const { caption, Scene } = SCENES[scene];
  return (
    <div
      className="overflow-hidden rounded-[16px] shadow-subtle"
      style={{ backgroundColor: INDIGO }}
      role="status"
      aria-label="Waking up the server. This usually takes under a minute."
    >
      {/* Keyed by scene, so each one's animations start from the beginning. */}
      <svg key={scene} viewBox="0 0 320 190" className="block w-full" aria-hidden="true">
        <Scene />
      </svg>
      <div className="px-4 pb-4">
        <p key={`caption-${scene}`} className="vl-rise text-center text-sm font-medium text-white" style={at(200)}>
          {caption}
        </p>
        <div className="mt-2 flex justify-center gap-1.5" aria-hidden="true">
          {SCENES.map((_, index) => (
            <span
              key={index}
              className="block h-1.5 rounded-full transition-all duration-[150ms]"
              style={{ width: index === scene ? 16 : 6, backgroundColor: index === scene ? AMBER : "rgba(199,210,254,0.4)" }}
            />
          ))}
        </div>
        <div className="mt-4 h-1 overflow-hidden rounded-full" style={{ backgroundColor: "rgba(199,210,254,0.2)" }}>
          <div
            className="h-full rounded-full transition-[width] duration-500 ease-linear"
            style={{ width: `${progress * 100}%`, backgroundColor: AMBER }}
          />
        </div>
        <p className="mt-2 text-center text-xs" style={{ color: LAVENDER }}>
          Waking the server · your slide is next
        </p>
      </div>
    </div>
  );
}
