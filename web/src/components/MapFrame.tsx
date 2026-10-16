import {
  type GeoProjection,
  geoDistance,
  geoEqualEarth,
  geoGraticule10,
  geoOrthographic,
  geoPath,
} from "d3-geo";
import type { FeatureCollection, GeoJsonProperties, Geometry } from "geojson";
import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import world from "../geo/world.json";
import { useMediaQuery } from "../hooks/use-media-query";
import {
  anchorOf,
  centerOn,
  easeInOut,
  facing,
  MAX_ZOOM,
  panBy,
  type Rotation,
  rotateBy,
  turnTowards,
  UNZOOMED,
  wheelFactor,
  type Zoom,
  zoomAbout,
  zoomed,
} from "../map-view";

interface WorldFile {
  source: string;
  topology: Topology<{ countries: GeometryCollection }>;
  /** Each country's name and population, and a point for one too small to draw. */
  facts: Record<string, { name: string; population: number; point?: [number, number] }>;
}

export const WORLD = world as unknown as WorldFile;
const WIDTH = 960;
/** A zoom button's step. */
const STEP = 1.6;
/** A pointer moving less than this, in pixels, clicks; more, it drags. */
const DRAG = 4;
const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
/** A frame this narrow draws the globe in a square, the map's height too little for it. */
const NARROW = "(max-width: 640px)";

/**
 * The countries' shapes, flat in the Equal Earth projection, which keeps their areas,
 * projected once: Natural Earth's 1:110m countries without Antarctica, and a point for
 * each country too small for them (Hong Kong, Singapore). Each country's tooltip points at
 * the center of its largest part (`anchors`), on either view.
 */
const MAP = (() => {
  const countries = feature(WORLD.topology, WORLD.topology.objects.countries) as FeatureCollection<
    Geometry,
    GeoJsonProperties
  >;
  const projection = geoEqualEarth().fitWidth(WIDTH, countries);
  const path = geoPath(projection);
  const height = Math.ceil(path.bounds(countries)[1][1]);
  const features = countries.features.map((country) => ({
    code: String(country.id ?? ""),
    country,
    d: path(country) ?? "",
  }));
  const anchors = new Map<string, [number, number]>();
  for (const { code, country } of features) if (code) anchors.set(code, anchorOf(country));
  for (const [code, facts] of Object.entries(WORLD.facts)) {
    if (facts.point) anchors.set(code, facts.point);
  }
  return { height, projection, features, anchors };
})();
const HEIGHT = MAP.height;
/** The globe fills the frame's height, a margin for its outline. */
const RADIUS = HEIGHT / 2 - 6;
const GRATICULE = geoGraticule10();

export const nameOf = (code: string) => WORLD.facts[code]?.name ?? code;

/** Mac keyboards name the key a symbol. */
const ZOOM_KEY = /Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘" : "Ctrl";

/** The globe's rotation and zoom. */
interface GlobeView {
  rotation: Rotation;
  scale: number;
}

interface Props {
  /** The globe, else the flat map. */
  globe: boolean;
  /** The map's text for screen readers. */
  label: string;
  /** Each country's fill (a class), memoized: the shapes are drawn again when it changes. */
  fillOf: (code: string) => string;
  /** The countries too small for the map that have papers, drawn as dots. */
  dots: readonly string[];
  pinned: string | null;
  onPin: (code: string | null) => void;
  /** The country the globe faces when it opens: the first of the metric shown. */
  lead: string | null;
  /** The tooltip's content for a country. */
  tip: (code: string) => ComponentChildren;
}

/**
 * The world map's drawing (UX-41, UX-43): flat or a globe, with its tooltip, zoomed by
 * the buttons, a pinch, or the wheel with Ctrl or ⌘ (the wheel alone scrolls the page),
 * moved by a drag, the globe turned by one. A country pinned from the table is brought
 * into view: the globe turns to it.
 */
export function MapFrame(props: Props) {
  const { globe, fillOf, dots, pinned, onPin } = props;
  const frame = useRef<HTMLDivElement>(null);
  const [reduced] = useState(() => window.matchMedia(REDUCED_MOTION).matches);
  // The viewBox's width: the flat map's, or the globe's square on a phone.
  const narrow = useMediaQuery(NARROW);
  const across = globe && narrow ? HEIGHT : WIDTH;

  // The flat map's zoom; the globe's rotation and zoom. The globe opens facing the first
  // country of the metric (where it opens: it does not follow the metric), turning to it,
  // tilted 30° at most.
  const [zoom, setZoom] = useState<Zoom>(UNZOOMED);
  const [home] = useState<Rotation>(() => {
    const anchor = props.lead ? MAP.anchors.get(props.lead) : undefined;
    return anchor ? facing([anchor[0], Math.max(-30, Math.min(30, anchor[1]))]) : [-10, -20];
  });
  const [view, setView] = useState<GlobeView>(() => ({
    rotation: globe && !reduced ? [home[0] + 120, home[1]] : home,
    scale: 1,
  }));
  const { rotation, scale } = view;
  const viewRef = useRef(view);
  viewRef.current = view;

  // The globe drawn again once a frame at most, however fast the pointer moves: each
  // drawing projects every country again.
  const pending = useRef<GlobeView | null>(null);
  const drawing = useRef(0);
  const moveGlobe = (change: (current: GlobeView) => GlobeView) => {
    pending.current = change(pending.current ?? viewRef.current);
    if (drawing.current) return;
    drawing.current = requestAnimationFrame(() => {
      drawing.current = 0;
      if (pending.current) setView(pending.current);
      pending.current = null;
    });
  };

  /** Turns the globe to a rotation, at once with reduced motion. */
  const turning = useRef(0);
  const turnTo = (to: Rotation, duration: number) => {
    cancelAnimationFrame(turning.current);
    if (reduced) {
      setView((current) => ({ ...current, rotation: to }));
      return;
    }
    let from: Rotation | null = null;
    let start = 0;
    const step = (now: number) => {
      if (from === null) {
        start = now;
        from = viewRef.current.rotation;
      }
      const t = Math.min(1, (now - start) / duration);
      const rotation = turnTowards(from, to, easeInOut(t));
      setView((current) => ({ ...current, rotation }));
      if (t < 1) turning.current = requestAnimationFrame(step);
    };
    turning.current = requestAnimationFrame(step);
  };
  useEffect(() => {
    if (globe) turnTo(home, 1400);
    return () => {
      cancelAnimationFrame(turning.current);
      cancelAnimationFrame(drawing.current);
    };
  }, []);

  // A country pinned from the table is brought into view; one pinned on the map is in it.
  const pinnedHere = useRef<string | null>(null);
  useEffect(() => {
    const here = pinnedHere.current;
    pinnedHere.current = null;
    if (pinned === null || pinned === here) return;
    const anchor = MAP.anchors.get(pinned);
    if (!anchor) return;
    if (globe) turnTo(facing(anchor), 800);
    else {
      const at = MAP.projection(anchor);
      if (at) setZoom((current) => centerOn(current, at, WIDTH, HEIGHT));
    }
  }, [pinned]);

  // The globe's projection, for its rotation and zoom.
  const projection = useMemo<GeoProjection>(
    () =>
      geoOrthographic()
        .translate([across / 2, HEIGHT / 2])
        .scale(RADIUS * scale)
        .rotate([rotation[0], rotation[1]])
        .clipAngle(90),
    [rotation, scale, across],
  );
  /** Where a country's anchor is in the frame's viewBox; `null` out of sight. */
  const anchorAt = (code: string): [number, number] | null => {
    const anchor = MAP.anchors.get(code);
    if (!anchor) return null;
    if (globe) {
      // Behind the globe.
      if (geoDistance(anchor, [-rotation[0], -rotation[1]]) > Math.PI / 2) return null;
      return projection(anchor);
    }
    const at = MAP.projection(anchor);
    return at ? zoomed(zoom, at) : null;
  };

  // Drawn again when the colors, the pinned country, or the globe's view change; the flat
  // map's zoom only moves its group.
  const shapes = useMemo(() => {
    const path = globe ? geoPath(projection) : null;
    return MAP.features.map(({ code, country, d }, index) => (
      <path
        key={code || `shape-${index}`}
        d={path ? (path(country) ?? "") : d}
        class={`world-map__shape ${fillOf(code)}${pinned === code ? " world-map__shape--pinned" : ""}`}
        data-code={code || undefined}
      />
    ));
  }, [fillOf, pinned, globe, projection]);
  const points = dots.flatMap((code) => {
    const at = globe ? anchorAt(code) : MAP.projection(MAP.anchors.get(code) ?? [0, 0]);
    return at
      ? [
          <circle
            key={code}
            cx={at[0]}
            cy={at[1]}
            r={globe ? 5 : 5 / zoom.k}
            class={`world-map__point ${fillOf(code)}${pinned === code ? " world-map__shape--pinned" : ""}`}
            data-code={code}
          />,
        ]
      : [];
  });

  // Pointers down on the map: one drags, two pinch.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [hovered, setHovered] = useState<{ code: string; x: number; y: number } | null>(null);
  const [hint, setHint] = useState(false);
  const hintTimer = useRef(0);
  useEffect(() => () => clearTimeout(hintTimer.current), []);

  /** The frame's pixels to the viewBox's units. */
  const unit = () => across / (frame.current?.clientWidth || across);
  const local = (event: PointerEvent | WheelEvent) => {
    const box = frame.current?.getBoundingClientRect();
    return { x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0) };
  };
  // The country under the pointer: the shape or dot it is over (`data-code`).
  const codeAt = (target: EventTarget | null): string | null =>
    target instanceof Element
      ? (target.closest<SVGElement>("[data-code]")?.dataset.code ?? null)
      : null;
  const hover = (event: PointerEvent) => {
    const code = codeAt(event.target);
    setHovered(code === null ? null : { code, ...local(event) });
  };
  const zoomBy = (factor: number, at: { x: number; y: number }) => {
    if (globe) {
      moveGlobe((current) => ({
        ...current,
        scale: Math.min(MAX_ZOOM, Math.max(1, current.scale * factor)),
      }));
    } else setZoom((current) => zoomAbout(current, factor, [at.x, at.y], WIDTH, HEIGHT));
  };
  const reset = () => {
    setZoom(UNZOOMED);
    setView((current) => ({ ...current, scale: 1 }));
    if (globe) turnTo(home, 800);
  };

  const onPointerDown = (event: PointerEvent) => {
    if (event.target instanceof Element && event.target.closest("button")) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    cancelAnimationFrame(turning.current);
    const at = local(event);
    pointers.current.set(event.pointerId, at);
    if (pointers.current.size === 1) gesture.current = { ...at, moved: false };
    else if (gesture.current) gesture.current.moved = true;
  };
  const onPointerMove = (event: PointerEvent) => {
    const previous = pointers.current.get(event.pointerId);
    const current = gesture.current;
    if (!(previous && current)) {
      hover(event);
      return;
    }
    const at = local(event);
    pointers.current.set(event.pointerId, at);
    if (pointers.current.size >= 2) {
      // A pinch: the distance between the first two fingers, before and after.
      const [a, b] = [...pointers.current.entries()];
      if (!(a && b)) return;
      const other = a[0] === event.pointerId ? b[1] : a[1];
      const before = Math.hypot(previous.x - other.x, previous.y - other.y);
      const after = Math.hypot(at.x - other.x, at.y - other.y);
      const middle = { x: ((at.x + other.x) / 2) * unit(), y: ((at.y + other.y) / 2) * unit() };
      if (before > 0) zoomBy(after / before, middle);
      setHovered(null);
      return;
    }
    if (!current.moved && Math.hypot(at.x - current.x, at.y - current.y) < DRAG) {
      hover(event);
      return;
    }
    if (!current.moved) {
      current.moved = true;
      frame.current?.setPointerCapture(event.pointerId);
      setDragging(true);
      setHovered(null);
    }
    const dx = (at.x - previous.x) * unit();
    const dy = (at.y - previous.y) * unit();
    if (globe) {
      moveGlobe((current) => ({
        ...current,
        rotation: rotateBy(current.rotation, dx, dy, RADIUS * current.scale),
      }));
    } else setZoom((moved) => panBy(moved, dx, dy, WIDTH, HEIGHT));
  };
  const onPointerEnd = (event: PointerEvent) => {
    // A click or a tap pins a country's tooltip; the table's buttons do from the keyboard.
    const click =
      event.type === "pointerup" && pointers.current.size === 1 && gesture.current?.moved === false;
    pointers.current.delete(event.pointerId);
    if (pointers.current.size === 0) {
      gesture.current = null;
      setDragging(false);
    }
    if (!click) return;
    const code = codeAt(event.target);
    if (code === null) return;
    pinnedHere.current = code;
    onPin(pinned === code ? null : code);
  };
  const onWheel = (event: WheelEvent) => {
    // The wheel alone scrolls the page, which the map is part of; with a key, or a
    // trackpad's pinch (a wheel with Ctrl), it zooms.
    if (!(event.ctrlKey || event.metaKey)) {
      setHint(true);
      clearTimeout(hintTimer.current);
      hintTimer.current = window.setTimeout(() => setHint(false), 1200);
      return;
    }
    event.preventDefault();
    cancelAnimationFrame(turning.current);
    const at = local(event);
    zoomBy(wheelFactor(event.deltaY, event.deltaMode, event.ctrlKey), {
      x: at.x * unit(),
      y: at.y * unit(),
    });
  };

  // The tooltip: the pointer's country, else the pinned one at its anchor.
  const width = frame.current?.clientWidth ?? across;
  const height = (width * HEIGHT) / across;
  const pinnedTip = (() => {
    if (hovered || pinned === null) return null;
    const at = anchorAt(pinned);
    if (!at) return null;
    const [x, y] = [(at[0] * width) / across, (at[1] * width) / across];
    return x < 0 || y < 0 || x > width || y > height ? null : { code: pinned, x, y };
  })();
  const shown = dragging ? null : (hovered ?? pinnedTip);
  // Dragged, the globe turns and a zoomed map moves; a finger on it then does not scroll.
  const zoomedIn = zoom.k > 1 || scale > 1;
  const movable = globe || zoomedIn;
  const r = RADIUS * scale;
  const center = { x: across / 2, y: HEIGHT / 2 };

  return (
    // The pointer's tooltips and gestures; the table below holds the same values for the
    // keyboard and screen readers, the buttons zoom.
    <div
      class={`world-map__frame${movable ? " world-map__frame--movable" : ""}${zoomedIn ? " world-map__frame--zoomed" : ""}${dragging ? " world-map__frame--dragging" : ""}`}
      ref={frame}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onPointerLeave={() => setHovered(null)}
      onWheel={onWheel}
    >
      <svg
        class="world-map__svg"
        viewBox={`0 0 ${across} ${HEIGHT}`}
        role="img"
        aria-label={props.label}
      >
        <defs>
          {/* Hatched where the metric says nothing, apart from any of its colors; as thin
              zoomed as not. */}
          <pattern
            id="world-map-hatch"
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
            patternTransform={`rotate(45) scale(${globe ? 1 : 1 / zoom.k})`}
          >
            <rect class="world-map__hatch-ground" width="4" height="4" />
            <rect class="world-map__hatch-line" width="1.4" height="4" />
          </pattern>
          {/* The sea lit from the top left: the countries keep their colors. */}
          <radialGradient id="world-map-sea" cx="38%" cy="32%" r="75%">
            <stop offset="0%" class="world-map__sea-light" />
            <stop offset="100%" class="world-map__sea-deep" />
          </radialGradient>
        </defs>
        {globe ? (
          <>
            <circle class="world-map__sea" cx={center.x} cy={center.y} r={r} />
            <path class="world-map__graticule" d={geoPath(projection)(GRATICULE) ?? ""} />
            {shapes}
            {points}
            <circle class="world-map__rim" cx={center.x} cy={center.y} r={r} />
          </>
        ) : (
          <g transform={`translate(${zoom.x} ${zoom.y}) scale(${zoom.k})`}>
            {shapes}
            {points}
          </g>
        )}
      </svg>
      {shown && (
        <div
          class={`world-map__tip${shown.x > width / 2 ? " world-map__tip--left" : ""}`}
          style={{ left: `${shown.x}px`, top: `${shown.y}px` }}
        >
          {props.tip(shown.code)}
        </div>
      )}
      <p class={`world-map__hint${hint ? " world-map__hint--shown" : ""}`} aria-hidden="true">
        {ZOOM_KEY} + scroll to zoom
      </p>
      <fieldset class="map-zoom">
        <legend class="visually-hidden">Zoom</legend>
        <button
          type="button"
          aria-label="Zoom in"
          title="Zoom in"
          onClick={() => zoomBy(STEP, center)}
        >
          +
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          title="Zoom out"
          onClick={() => zoomBy(1 / STEP, center)}
        >
          −
        </button>
        <button
          type="button"
          aria-label={globe ? "Show the whole globe" : "Show the whole map"}
          title="Reset"
          onClick={reset}
        >
          ⤢
        </button>
      </fieldset>
    </div>
  );
}
