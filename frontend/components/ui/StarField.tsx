/**
 * The sky behind every screen.
 *
 * Four layers of stars and three shooting ones, all of it decorative and
 * all of it in CSS — see globals.css for why it is drawn as gradients on
 * seven elements rather than as a hundred positioned dots.
 *
 * Fixed to the viewport, so it stays put while the page scrolls. That is
 * deliberate: a starfield that scrolls with the content reads as wallpaper
 * being dragged, and one that parallaxes competes with the reading.
 *
 * Not a client component. There is no state, no effect and no interaction
 * here; it renders identically on the server and never needs hydrating.
 */
export function StarField() {
  return (
    <div className="stars-field" aria-hidden>
      <div className="stars-a" />
      <div className="stars-b" />
      <div className="stars-c" />
      <div className="stars-d" />
      {/* Start off the left edge on three different lines, so the three
          cycles never look like the same streak repeating. */}
      <span className="shooting-star" style={{ top: "11%", left: "-12%" }} />
      <span className="shooting-star" style={{ top: "41%", left: "8%" }} />
      <span className="shooting-star" style={{ top: "68%", left: "-6%" }} />
    </div>
  );
}
