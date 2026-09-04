/** Procedural furniture for the cinematic scene.
 *
 * Why generated geometry instead of GLTF models:
 *   * A photoreal sofa GLTF with PBR textures is 3–15 MB. Seven of those turns
 *     a 145 KB hero into a multi-megabyte scene, on a demo whose audience is
 *     on Iranian mobile connections.
 *   * These are box/cylinder primitives with rounded proportions and honest
 *     materials. At the camera distances the scroll path uses, silhouette and
 *     lighting carry the read — not surface micro-detail.
 *   * Every piece is parameterised in centimetres so it matches the real
 *     product dimensions the recommender already stores (width_cm/depth_cm/
 *     height_cm). The scene is therefore dimensionally truthful, which is the
 *     product's actual selling point.
 *
 * Scene units: 1 unit = 1 metre.
 */
import { useMemo } from "react";
import * as THREE from "three";

/* --------------------------------------------------------------- materials */

export const PALETTE = {
  wall: "#EFE9E1",
  floor: "#C69C6D",
  rug: "#D9CFC0",
  rugPattern: "#8C7B6B",
  sofa: "#D8CFC2",
  cushionA: "#C06A3C",
  cushionB: "#8A6A4F",
  wood: "#6B4A2F",
  metal: "#B08D57",
  plant: "#3E6B4A",
  pot: "#B4715A",
  art: "#4A6274",
  glass: "#BFD8E8",
} as const;

function useStandard(color: string, roughness = 0.85, metalness = 0.02) {
  return useMemo(
    () => new THREE.MeshStandardMaterial({ color, roughness, metalness }),
    [color, roughness, metalness],
  );
}

/* ------------------------------------------------------------------- pieces */

type Vec = [number, number, number];

/** Three-seat sofa. Default dimensions mirror a real catalogue entry
 *  (180×88×94 cm — the "Contemporary Modern Sofa" the API returns). */
export function Sofa({
  position = [0, 0, 0] as Vec,
  rotation = [0, 0, 0] as Vec,
  width = 1.8,
  depth = 0.88,
  height = 0.94,
}) {
  const body = useStandard(PALETTE.sofa, 0.95);
  const wood = useStandard(PALETTE.wood, 0.6);
  const cushA = useStandard(PALETTE.cushionA, 0.9);
  const cushB = useStandard(PALETTE.cushionB, 0.9);

  const seatH = 0.42;
  const backH = height - seatH;
  const armW = 0.16;

  return (
    <group position={position} rotation={rotation}>
      {/* seat base */}
      <mesh material={body} position={[0, seatH * 0.72, 0]} castShadow receiveShadow>
        <boxGeometry args={[width, seatH * 0.55, depth]} />
      </mesh>
      {/* seat cushions */}
      {[-1, 0, 1].map((i) => (
        <mesh
          key={i}
          material={body}
          position={[i * (width / 3.1), seatH + 0.05, 0.02]}
          castShadow
        >
          <boxGeometry args={[width / 3.3, 0.16, depth * 0.82]} />
        </mesh>
      ))}
      {/* backrest */}
      <mesh
        material={body}
        position={[0, seatH + backH / 2, -depth / 2 + 0.11]}
        castShadow
      >
        <boxGeometry args={[width, backH, 0.22]} />
      </mesh>
      {/* arms */}
      {[-1, 1].map((s) => (
        <mesh
          key={s}
          material={body}
          position={[s * (width / 2 - armW / 2), seatH + 0.1, 0]}
          castShadow
        >
          <boxGeometry args={[armW, 0.32, depth]} />
        </mesh>
      ))}
      {/* accent cushions — the colour the recommender scores against */}
      <mesh material={cushA} position={[-width / 3.4, seatH + 0.26, -0.14]} rotation={[0.2, 0.1, 0.12]} castShadow>
        <boxGeometry args={[0.36, 0.36, 0.12]} />
      </mesh>
      <mesh material={cushB} position={[width / 3.4, seatH + 0.26, -0.14]} rotation={[0.2, -0.1, -0.12]} castShadow>
        <boxGeometry args={[0.34, 0.34, 0.12]} />
      </mesh>
      {/* legs */}
      {[
        [-1, -1],
        [1, -1],
        [-1, 1],
        [1, 1],
      ].map(([sx, sz], i) => (
        <mesh
          key={i}
          material={wood}
          position={[sx * (width / 2 - 0.14), 0.09, sz * (depth / 2 - 0.12)]}
          castShadow
        >
          <cylinderGeometry args={[0.032, 0.026, 0.18, 10]} />
        </mesh>
      ))}
    </group>
  );
}

/** Walnut coffee table (120×60×40 cm). */
export function CoffeeTable({ position = [0, 0, 0] as Vec, rotation = [0, 0, 0] as Vec }) {
  const wood = useStandard(PALETTE.wood, 0.5);
  return (
    <group position={position} rotation={rotation}>
      <mesh material={wood} position={[0, 0.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[1.2, 0.05, 0.6]} />
      </mesh>
      {[
        [-1, -1],
        [1, -1],
        [-1, 1],
        [1, 1],
      ].map(([sx, sz], i) => (
        <mesh key={i} material={wood} position={[sx * 0.52, 0.19, sz * 0.24]} castShadow>
          <boxGeometry args={[0.06, 0.38, 0.06]} />
        </mesh>
      ))}
    </group>
  );
}

/** Patterned area rug — flat geometry, so it costs almost nothing. */
export function Rug({ position = [0, 0.005, 0] as Vec, width = 3.0, depth = 2.0 }) {
  const base = useStandard(PALETTE.rug, 1);
  const pattern = useStandard(PALETTE.rugPattern, 1);
  return (
    <group position={position}>
      <mesh material={base} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width, depth]} />
      </mesh>
      {/* concentric border bands read as a Persian rug from camera distance */}
      {[0.88, 0.72].map((k, i) => (
        <mesh
          key={i}
          material={pattern}
          position={[0, 0.001 + i * 0.001, 0]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <ringGeometry args={[(width * k) / 2 - 0.04, (width * k) / 2, 4, 1]} />
        </mesh>
      ))}
    </group>
  );
}

/** Framed wall art. */
export function WallArt({
  position = [0, 1.6, 0] as Vec,
  rotation = [0, 0, 0] as Vec,
  width = 0.6,
  height = 0.8,
  color = PALETTE.art as string,
}) {
  const frame = useStandard(PALETTE.wood, 0.55);
  const canvas = useStandard(color, 0.9);
  return (
    <group position={position} rotation={rotation}>
      <mesh material={frame} castShadow>
        <boxGeometry args={[width, height, 0.03]} />
      </mesh>
      <mesh material={canvas} position={[0, 0, 0.018]}>
        <planeGeometry args={[width - 0.07, height - 0.07]} />
      </mesh>
    </group>
  );
}

/** Floor lamp with a warm shade. */
export function FloorLamp({ position = [0, 0, 0] as Vec }) {
  const metal = useStandard(PALETTE.metal, 0.35, 0.75);
  const shade = useStandard("#F0E4CE", 0.8);
  return (
    <group position={position}>
      <mesh material={metal} position={[0, 0.02, 0]} castShadow>
        <cylinderGeometry args={[0.16, 0.18, 0.04, 20]} />
      </mesh>
      <mesh material={metal} position={[0, 0.75, 0]} castShadow>
        <cylinderGeometry args={[0.018, 0.018, 1.5, 12]} />
      </mesh>
      <mesh material={shade} position={[0, 1.58, 0]} castShadow>
        <cylinderGeometry args={[0.2, 0.26, 0.3, 20, 1, true]} />
      </mesh>
      {/* the lamp actually emits — sells the "evening interior" mood */}
      <pointLight position={[0, 1.5, 0]} intensity={6} distance={4.5} color="#FFD9A0" />
    </group>
  );
}

/** Potted fiddle-leaf style plant. */
export function Plant({ position = [0, 0, 0] as Vec, scale = 1 }) {
  const pot = useStandard(PALETTE.pot, 0.85);
  const leaf = useStandard(PALETTE.plant, 0.75);
  const leaves = useMemo(
    () =>
      Array.from({ length: 9 }, (_, i) => {
        const a = (i / 9) * Math.PI * 2;
        const h = 0.55 + (i % 3) * 0.22;
        return { a, h, r: 0.16 + (i % 2) * 0.1 };
      }),
    [],
  );
  return (
    <group position={position} scale={scale}>
      <mesh material={pot} position={[0, 0.18, 0]} castShadow>
        <cylinderGeometry args={[0.19, 0.14, 0.36, 16]} />
      </mesh>
      <mesh material={leaf} position={[0, 0.6, 0]}>
        <cylinderGeometry args={[0.014, 0.02, 0.55, 8]} />
      </mesh>
      {leaves.map((l, i) => (
        <mesh
          key={i}
          material={leaf}
          position={[Math.cos(l.a) * l.r, 0.4 + l.h, Math.sin(l.a) * l.r]}
          rotation={[0.35, l.a, 0.25]}
          castShadow
        >
          <sphereGeometry args={[0.15, 10, 8]} />
        </mesh>
      ))}
    </group>
  );
}

/** Bookshelf with coloured spines. */
export function Shelf({ position = [0, 0, 0] as Vec, rotation = [0, 0, 0] as Vec }) {
  const wood = useStandard(PALETTE.wood, 0.6);
  const books = ["#8C4A3C", "#3E5A6B", "#7A6A4F", "#4A6B4F", "#8A7250"];
  return (
    <group position={position} rotation={rotation}>
      <mesh material={wood} position={[0, 0.9, 0]} castShadow>
        <boxGeometry args={[0.9, 1.8, 0.28]} />
      </mesh>
      {[0.45, 0.9, 1.35].map((y, r) => (
        <group key={r}>
          {books.map((c, i) => (
            <mesh
              key={i}
              position={[-0.32 + i * 0.15, y + 0.13, 0.06]}
              castShadow
            >
              <boxGeometry args={[0.06, 0.24, 0.16]} />
              <meshStandardMaterial color={c} roughness={0.9} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}
