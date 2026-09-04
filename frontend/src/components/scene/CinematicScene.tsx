/** Scroll-driven cinematic walkthrough.
 *
 * The camera follows a fixed spline: it starts outside the building, moves
 * through the window opening, glides past the sofa and rug, turns toward the
 * art wall and settles at a seated viewpoint. Scroll position drives progress
 * along that curve — nothing animates on a timer, so the user is always in
 * control and can scrub backwards.
 *
 * Performance posture (this is a demo whose Lighthouse score is quoted in a
 * proposal, so every choice below is deliberate):
 *   * The whole module is behind React.lazy at the call site, so the landing
 *     page's initial bundle is untouched.
 *   * `frameloop="demand"` — the renderer only draws when scroll actually
 *     changed. A static page costs zero GPU frames, unlike a default rAF loop.
 *   * DPR is clamped to 1.5 and shadows are disabled below a hardware
 *     threshold; very weak devices are refused outright by the parent.
 *   * Geometry is procedural primitives (see furniture.tsx) — no GLTF download.
 */
import { Suspense, useMemo, useRef, useState, useEffect } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import {
  Sofa,
  CoffeeTable,
  Rug,
  WallArt,
  FloorLamp,
  Plant,
  Shelf,
  PALETTE,
} from "./furniture";

/* ------------------------------------------------------------------ camera */

/** Waypoints of the fly-through, in metres.
 *  z decreases as we move deeper into the room; the window sits at z = 4. */
const CAMERA_PATH: THREE.Vector3[] = [
  new THREE.Vector3(1.6, 3.0, 13.0), // outside, above street level
  new THREE.Vector3(0.9, 2.1, 8.4), // approaching the facade
  new THREE.Vector3(0.35, 1.62, 5.0), // lining up with the opening
  new THREE.Vector3(0.05, 1.5, 3.4), // crossing the glazing plane
  new THREE.Vector3(-0.5, 1.4, 1.6), // inside — the room opens up
  new THREE.Vector3(-1.7, 1.15, 0.1), // gliding past the sofa arm
  new THREE.Vector3(-1.25, 0.95, -1.5), // low over the rug and table
  new THREE.Vector3(0.6, 1.25, -2.15), // rising, turning to the art wall
];

/** Where the camera looks at each waypoint. Decoupling look-at from position
 *  is what makes it read as a filmed shot rather than a rollercoaster. */
const LOOK_PATH: THREE.Vector3[] = [
  new THREE.Vector3(0, 1.7, 4.0),
  new THREE.Vector3(0, 1.55, 1.5),
  new THREE.Vector3(0, 1.4, -1.5),
  new THREE.Vector3(-0.3, 1.25, -2.4),
  new THREE.Vector3(-1.0, 0.95, -2.6),
  new THREE.Vector3(-1.2, 0.55, -2.5),
  new THREE.Vector3(-0.2, 0.45, -2.6),
  new THREE.Vector3(1.3, 1.6, -3.6),
];

function CameraRig({ progress }: { progress: React.MutableRefObject<number> }) {
  const { camera, invalidate } = useThree();
  const posCurve = useMemo(
    () => new THREE.CatmullRomCurve3(CAMERA_PATH, false, "catmullrom", 0.4),
    [],
  );
  const lookCurve = useMemo(
    () => new THREE.CatmullRomCurve3(LOOK_PATH, false, "catmullrom", 0.4),
    [],
  );
  const smoothed = useRef(0);
  const target = useMemo(() => new THREE.Vector3(), []);

  useFrame(() => {
    // Critically damped follow: the raw scroll value is stepped (wheel deltas),
    // and sampling the curve at it directly makes the shot stutter.
    const prev = smoothed.current;
    smoothed.current += (progress.current - smoothed.current) * 0.075;
    const t = THREE.MathUtils.clamp(smoothed.current, 0, 1);

    camera.position.copy(posCurve.getPointAt(t));
    target.copy(lookCurve.getPointAt(t));
    camera.lookAt(target);

    // Keep drawing while still catching up, then stop — this is what makes
    // frameloop="demand" cheap on an idle page.
    if (Math.abs(progress.current - smoothed.current) > 0.0005 || Math.abs(prev - smoothed.current) > 0.0005) {
      invalidate();
    }
  });

  return null;
}

/* -------------------------------------------------------------------- room */

function Room({ shadows }: { shadows: boolean }) {
  const wall = useMemo(
    () => new THREE.MeshStandardMaterial({ color: PALETTE.wall, roughness: 0.95 }),
    [],
  );
  const floor = useMemo(
    () => new THREE.MeshStandardMaterial({ color: PALETTE.floor, roughness: 0.7 }),
    [],
  );
  const glass = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: PALETTE.glass,
        transparent: true,
        opacity: 0.22,
        roughness: 0.1,
        metalness: 0.1,
      }),
    [],
  );

  const W = 6.5; // room width
  const D = 7.5; // room depth
  const H = 3.0; // ceiling height

  return (
    <group>
      {/* floor */}
      <mesh material={floor} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow={shadows}>
        <planeGeometry args={[W, D]} />
      </mesh>
      {/* ceiling */}
      <mesh material={wall} rotation={[Math.PI / 2, 0, 0]} position={[0, H, 0]}>
        <planeGeometry args={[W, D]} />
      </mesh>
      {/* back wall (the art wall) */}
      <mesh material={wall} position={[0, H / 2, -D / 2]} receiveShadow={shadows}>
        <planeGeometry args={[W, H]} />
      </mesh>
      {/* side walls */}
      <mesh material={wall} rotation={[0, Math.PI / 2, 0]} position={[-W / 2, H / 2, 0]} receiveShadow={shadows}>
        <planeGeometry args={[D, H]} />
      </mesh>
      <mesh material={wall} rotation={[0, -Math.PI / 2, 0]} position={[W / 2, H / 2, 0]} receiveShadow={shadows}>
        <planeGeometry args={[D, H]} />
      </mesh>

      {/* front wall with a window opening the camera flies through: four
          panels leaving a gap, cheaper and cleaner than CSG subtraction */}
      <group position={[0, 0, D / 2]}>
        <mesh material={wall} position={[-2.15, H / 2, 0]}>
          <planeGeometry args={[2.2, H]} />
        </mesh>
        <mesh material={wall} position={[2.15, H / 2, 0]}>
          <planeGeometry args={[2.2, H]} />
        </mesh>
        <mesh material={wall} position={[0, 2.72, 0]}>
          <planeGeometry args={[2.1, 0.56]} />
        </mesh>
        <mesh material={wall} position={[0, 0.2, 0]}>
          <planeGeometry args={[2.1, 0.4]} />
        </mesh>
        {/* Glazing, split either side of the flight line: a centred mullion
            would sit directly in front of the lens for the whole approach. */}
        <mesh material={glass} position={[-0.78, 1.52, 0.01]}>
          <planeGeometry args={[0.54, 2.24]} />
        </mesh>
        <mesh material={glass} position={[0.78, 1.52, 0.01]}>
          <planeGeometry args={[0.54, 2.24]} />
        </mesh>
        {[-0.5, 0.5].map((x) => (
          <mesh key={x} position={[x, 1.52, 0.02]}>
            <boxGeometry args={[0.05, 2.24, 0.05]} />
            <meshStandardMaterial color={PALETTE.wood} roughness={0.6} />
          </mesh>
        ))}
      </group>
    </group>
  );
}

/* ------------------------------------------------------------------ content */

function SceneContents({ shadows }: { shadows: boolean }) {
  return (
    <>
      {/* Warm late-afternoon key light coming through the window. */}
      <directionalLight
        position={[2.5, 4.2, 6]}
        intensity={2.4}
        color="#FFE2B8"
        castShadow={shadows}
        shadow-mapSize={[1024, 1024]}
        shadow-camera-near={0.5}
        shadow-camera-far={20}
        shadow-camera-left={-6}
        shadow-camera-right={6}
        shadow-camera-top={6}
        shadow-camera-bottom={-6}
      />
      <ambientLight intensity={0.85} color="#FFF3E4" />
      <hemisphereLight args={["#FFF6E8", "#8A7358", 0.55]} />

      <Room shadows={shadows} />

      <Rug position={[-0.9, 0.006, -1.2]} width={3.1} depth={2.1} />
      <Sofa position={[-1.0, 0, -2.45]} rotation={[0, 0, 0]} />
      <CoffeeTable position={[-0.95, 0, -1.15]} />
      <FloorLamp position={[0.75, 0, -2.5]} />
      <Plant position={[-2.55, 0, -2.2]} scale={1.05} />
      <Plant position={[2.35, 0, 1.4]} scale={0.85} />
      <Shelf position={[2.45, 0, -2.9]} rotation={[0, -0.35, 0]} />

      <WallArt position={[0.9, 1.75, -3.72]} width={0.72} height={0.92} color="#4A6274" />
      <WallArt position={[1.85, 1.62, -3.72]} width={0.5} height={0.62} color="#8C6A4A" />
    </>
  );
}

/* ------------------------------------------------------------------- shell */

export default function CinematicScene({
  progress,
}: {
  /** 0 → 1 along the scroll-linked section. */
  progress: React.MutableRefObject<number>;
}) {
  // Shadow maps are the single most expensive thing here; drop them on
  // low-core / low-memory devices rather than shipping a slideshow.
  const [shadows] = useState(() => {
    if (typeof navigator === "undefined") return false;
    const cores = navigator.hardwareConcurrency ?? 4;
    const mem = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 4;
    return cores >= 6 && mem >= 4;
  });

  return (
    <Canvas
      // Only render when something changed — see CameraRig.invalidate().
      frameloop="demand"
      shadows={shadows}
      dpr={[1, 1.5]}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      camera={{ fov: 58, near: 0.1, far: 60, position: [1.2, 2.6, 11.5] }}
      style={{ width: "100%", height: "100%", display: "block" }}
    >
      <color attach="background" args={["#E8DFD3"]} />
      <fog attach="fog" args={["#E8DFD3", 12, 26]} />
      <Suspense fallback={null}>
        <SceneContents shadows={shadows} />
      </Suspense>
      <CameraRig progress={progress} />
    </Canvas>
  );
}

/** Re-render the canvas once on mount so the first frame is not blank when
 *  frameloop is "demand". */
export function useInvalidateOnMount() {
  const { invalidate } = useThree();
  useEffect(() => invalidate(), [invalidate]);
}
