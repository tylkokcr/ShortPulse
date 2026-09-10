/**
 * A waveform along the bottom of the page.
 *
 * The brief was something marginal and specific rather than another
 * generic texture, and the most specific thing this product has is the
 * material it works in: speech. So the floor of the landing page is an
 * audio waveform — the same shape the logo is a fragment of, and the same
 * shape the captions are timed against.
 *
 * The envelope is not noise. It is a slow carrier with a syllable rate on
 * top and a little jitter, which is what makes it read as somebody
 * talking rather than as a bar chart: long swells with gaps between them,
 * and a few bars flat on the floor where the speaker breathes.
 *
 * Drawn twice inside a track twice the width and translated by half of it,
 * so the loop lands on the copy and the seam is invisible — the same
 * trick, and the same keyframe, as the marquee. The first six bars are
 * eased into the last one for the same reason.
 *
 * Static markup, no client hooks: nothing here reacts to anything, so it
 * renders on the server and never hydrates.
 */
const BARS = [
  0.391, 0.454, 0.444, 0.398, 0.408, 0.521, 0.844, 1.0, 0.902, 0.626, 0.6, 0.556, 0.866, 0.982,
  0.966, 0.588, 0.371, 0.293, 0.346, 0.604, 0.665, 0.365, 0.18, 0.1, 0.1, 0.1, 0.435, 0.369, 0.208,
  0.1, 0.1, 0.133, 0.348, 0.633, 0.517, 0.405, 0.246, 0.181, 0.49, 0.81, 1.0, 0.789, 0.591, 0.44,
  0.641, 0.898, 1.0, 1.0, 0.724, 0.53, 0.448, 0.678, 0.867, 0.9, 0.593, 0.155, 0.102, 0.191, 0.402,
  0.484, 0.424, 0.1, 0.1, 0.1, 0.1, 0.241, 0.514, 0.413, 0.1, 0.1, 0.115, 0.391,
];

const STEP = 9;
const BAR_W = 3;
const HEIGHT = 56;
const WIDTH = BARS.length * STEP;

function Wave() {
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width={WIDTH}
      height={HEIGHT}
      preserveAspectRatio="none"
      className="h-full w-1/2 shrink-0"
      aria-hidden
    >
      {BARS.map((value, i) => {
        const h = Math.max(2, value * HEIGHT);
        return (
          <rect
            key={i}
            x={i * STEP}
            y={HEIGHT - h}
            width={BAR_W}
            height={h}
            rx={BAR_W / 2}
            // Taller bars sit slightly brighter, the way a louder moment
            // reads as a stronger mark in any real waveform view.
            fill={`rgba(255,255,255,${(0.05 + value * 0.09).toFixed(3)})`}
          />
        );
      })}
    </svg>
  );
}

export function WaveFloor() {
  return (
    <div className="wave-floor" aria-hidden>
      <div className="wave-track">
        <Wave />
        <Wave />
      </div>
    </div>
  );
}
