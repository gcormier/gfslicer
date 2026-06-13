// Client-side port of gridfinity_slicer/core.py, backed by the manifold-3d WASM
// build (the same C++ engine the Python tool welds with). No server required.
//
// The GridFinity geometry repeats with a true 42 mm period, so cutting at two
// grid-aligned planes an exact multiple of 42 mm apart exposes identical
// cross-sections that weld with no gap. See core.py for the full rationale.

import Module from "https://unpkg.com/manifold-3d@3.1.1/manifold.js";

export const GRID = 42.0;
const AXES = { x: 0, y: 1, z: 2 };

let _wasm = null;

// Load and initialise the WASM module once; safe to call repeatedly.
export async function initManifold() {
  if (_wasm) return _wasm;
  const wasm = await Module({
    locateFile: () => "https://unpkg.com/manifold-3d@3.1.1/manifold.wasm",
  });
  wasm.setup();
  _wasm = wasm;
  return _wasm;
}

function axisIndex(axis) {
  const ax = AXES[String(axis).toLowerCase()];
  if (ax === undefined) throw new Error(`axis must be one of x, y, z (got ${axis})`);
  return ax;
}

// Whole 42 mm cells along an axis, allowing `tol` mm under a full multiple to
// still count (the GridFinity footprint gap). Mirrors core.inspect.
function unitsFor(size, tol = 0.5) {
  return size.map((s) => Math.max(Math.floor((s + tol) / GRID), 0));
}

// Bounding box + grid mapping from a triangle-soup position array (the
// Float32Array from three.js geometry.attributes.position). Pure JS, no WASM.
export function inspectPositions(positions, tol = 0.5) {
  const lo = [Infinity, Infinity, Infinity];
  const hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3) {
    for (let k = 0; k < 3; k++) {
      const v = positions[i + k];
      if (v < lo[k]) lo[k] = v;
      if (v > hi[k]) hi[k] = v;
    }
  }
  const size = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]];
  const units = unitsFor(size, tol);
  return { lo, hi, size, units: { x: units[0], y: units[1], z: units[2] } };
}

// Human-readable summary, matching core.GridInfo.describe.
export function describe(info) {
  const [x, y, z] = info.size;
  const ux = info.units.x, uy = info.units.y;
  const lines = [
    `Bounding box : ${x.toFixed(2)} x ${y.toFixed(2)} x ${z.toFixed(2)} mm`,
    `Grid (42 mm) : ${ux} x ${uy} units in XY  (Z = ${z.toFixed(2)} mm)`,
  ];
  const sizes = [x, y];
  [["X", ux], ["Y", uy]].forEach(([label, n], i) => {
    const r = sizes[i] - n * GRID;
    let note;
    if (Math.abs(r) < 1e-3) note = "exact";
    else if (r < 0) note = `${(-r).toFixed(2)} mm short of ${n} whole units (footprint gap)`;
    else note = `${r.toFixed(2)} mm over ${n} whole units (not a clean grid count)`;
    lines.push(`  ${label}: ${n} unit(s), ${note}`);
  });
  return lines.join("\n");
}

// Build a Manifold from triangle-soup positions. STL stores each triangle with
// its own 3 vertices, so we hand manifold a soup and let Mesh.merge() weld
// coincident verts into the shared topology a boolean needs.
function manifoldFromPositions(wasm, positions) {
  const verts = positions instanceof Float32Array ? positions : new Float32Array(positions);
  const nVert = verts.length / 3;
  const triVerts = new Uint32Array(nVert);
  for (let i = 0; i < nVert; i++) triVerts[i] = i;
  const mesh = new wasm.Mesh({ numProp: 3, vertProperties: verts, triVerts });
  mesh.merge();
  return new wasm.Manifold(mesh);
}

// Pull a manifold's geometry into JS-owned typed arrays. We copy (via the
// typed-array constructors) so the result stays valid after the source
// manifold's WASM memory is freed.
function extractMesh(manifoldObj) {
  const m = manifoldObj.getMesh();
  return {
    numProp: 3,
    vertProperties: new Float32Array(m.vertProperties),
    triVerts: new Uint32Array(m.triVerts),
  };
}

// Remove `count` 42 mm cells starting at `cell` along `axis` and weld the rest
// into a single watertight solid. Mirrors core.cut. Returns a manifold Mesh
// ({ numProp, vertProperties, triVerts }) ready for STL export.
//
// initManifold() must have resolved first.
export function cutPositions(positions, axis, cell, count = 1) {
  const wasm = _wasm;
  if (!wasm) throw new Error("manifold not initialised — await initManifold() first");
  if (count < 1) throw new Error("count must be >= 1");

  const ax = axisIndex(axis);
  const solid = manifoldFromPositions(wasm, positions);
  const cleanup = [solid];

  try {
    const box = solid.boundingBox();
    const lo = box.min;
    const size = [box.max[0] - lo[0], box.max[1] - lo[1], box.max[2] - lo[2]];
    const total = unitsFor(size)[ax];
    const axisName = "xyz"[ax].toUpperCase();

    if (total < count) {
      throw new Error(`mesh is only ${total} unit(s) along ${axisName}; cannot remove ${count}`);
    }
    if (!(cell >= 0 && cell <= total - count)) {
      throw new Error(
        `cell must be in 0..${total - count} for count=${count} ` +
        `(mesh has ${total} units along ${axisName})`
      );
    }

    const start = lo[ax] + cell * GRID;
    const end = start + count * GRID;
    const width = end - start;

    const leftNormal = [0, 0, 0]; leftNormal[ax] = -1;   // keep <= start
    const rightNormal = [0, 0, 0]; rightNormal[ax] = 1;  // keep >= end
    let left = solid.trimByPlane(leftNormal, -start);
    let right = solid.trimByPlane(rightNormal, end);
    cleanup.push(left, right);

    const leftEmpty = left.isEmpty();
    const rightEmpty = right.isEmpty();
    if (leftEmpty && rightEmpty) {
      throw new Error("slice produced no geometry -- check axis/cell/count");
    }

    // Removing the first or last cell leaves a single piece; just shift it
    // (no weld, so no seam overlap needed).
    if (leftEmpty || rightEmpty) {
      if (rightEmpty) {
        // left already spans [lo, start]; nothing to slide.
        return extractMesh(left);
      }
      // left empty (removed the first cell): slide the surviving far piece back.
      const shift = [0, 0, 0]; shift[ax] = -width;
      const moved = right.translate(shift);
      cleanup.push(moved);
      return extractMesh(moved);
    }

    // Both pieces present: weld them. Coincident cut faces make manifold leave
    // two touching shells (genus -1) instead of one solid, so we need a small
    // overlap at the seam. We get it by extending the NEAR piece by `eps` into
    // the removed slab while sliding the far piece back by exactly `width`. The
    // seam spacing is a whole multiple of 42 mm, so the overlap region has
    // identical cross-sections and fuses cleanly -- and because only the near
    // piece grows (the far extent is untouched), the overall dimension stays
    // exact. `eps` is bbox-relative, comfortably above manifold's precision
    // floor (~bbox*1e-7).
    const eps = Math.max(size[0], size[1], size[2]) * 1e-6;
    const leftWeld = solid.trimByPlane(leftNormal, -(start + eps));
    cleanup.push(leftWeld);
    const shift = [0, 0, 0]; shift[ax] = -width;
    const moved = right.translate(shift);
    cleanup.push(moved);

    const joined = wasm.Manifold.union(leftWeld, moved);
    cleanup.push(joined);
    if (joined.isEmpty()) throw new Error("weld produced an empty mesh");
    return extractMesh(joined);
  } finally {
    for (const obj of cleanup) {
      try { obj.delete && obj.delete(); } catch { /* already freed */ }
    }
  }
}
