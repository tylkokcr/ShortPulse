import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

/**
 * ESLint 9 reads this file and nothing else — there is no `.eslintrc` and
 * there never was one here, which is why linting silently did nothing for
 * the life of this project. `next lint` was removed in Next 16, so the old
 * `lint` script had also been failing outright; both halves are replaced
 * here by a config ESLint can actually load and a script that runs it.
 *
 * The two imports are the flat-config exports of `eslint-config-next`,
 * pinned to the same major as Next itself. core-web-vitals is the stricter
 * of Next's two presets — it promotes the rules that correspond to real
 * loading and layout problems from warnings to errors, which is the point
 * of turning linting on at all.
 */
const config = [
  {
    // Generated, vendored, or not ours: build output, dependencies, the
    // types file Next rewrites on every dev start, and the static assets.
    // `**/` matters: a stray `next dev` from the wrong directory leaves a
    // second build tree at frontend/frontend/.next, and a bare `.next/**`
    // only matches the one at the root — ESLint went and linted 23MB of
    // compiled vendor chunks, reporting 4,600 problems in code nobody
    // here wrote.
    ignores: ["**/.next/**", "**/node_modules/**", "next-env.d.ts", "public/**"],
  },
  ...coreWebVitals,
  ...typescript,
  {
    rules: {
      /**
       * Ten call sites trip this, and all ten are the pattern it is
       * hardest to replace: read something that only exists in a browser
       * — localStorage, matchMedia, an element's size — after mount, and
       * put it in state. It cannot run during SSR, so the lazy-initialiser
       * form the rule suggests is not available; that is also precisely
       * why the markup and the first client render would otherwise
       * disagree. Kept visible as a warning rather than switched off,
       * because the rule is right about cascading renders in general and
       * a new one should be argued with rather than inherited.
       */
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default config;
