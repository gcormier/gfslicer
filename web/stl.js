// Binary STL writer. Input is a manifold mesh: vertProperties (Float32Array,
// xyz per vertex, 3 props) and triVerts (Uint32Array, 3 indices per triangle).
// STL parsing on the way in is handled by three.js STLLoader in index.html, so
// this module only needs to write.

export function meshToBinarySTL(vertProperties, triVerts) {
  const nTri = triVerts.length / 3;
  const buf = new ArrayBuffer(84 + nTri * 50);
  const dv = new DataView(buf);

  // 80-byte header (free-form text), then little-endian triangle count.
  const tag = "gfslicer";
  for (let i = 0; i < tag.length; i++) dv.setUint8(i, tag.charCodeAt(i));
  dv.setUint32(80, nTri, true);

  let off = 84;
  for (let t = 0; t < nTri; t++) {
    const a = triVerts[t * 3], b = triVerts[t * 3 + 1], c = triVerts[t * 3 + 2];
    const ax = vertProperties[a * 3], ay = vertProperties[a * 3 + 1], az = vertProperties[a * 3 + 2];
    const bx = vertProperties[b * 3], by = vertProperties[b * 3 + 1], bz = vertProperties[b * 3 + 2];
    const cx = vertProperties[c * 3], cy = vertProperties[c * 3 + 1], cz = vertProperties[c * 3 + 2];

    // Face normal = normalize((b-a) x (c-a)).
    const ux = bx - ax, uy = by - ay, uz = bz - az;
    const vx = cx - ax, vy = cy - ay, vz = cz - az;
    let nx = uy * vz - uz * vy;
    let ny = uz * vx - ux * vz;
    let nz = ux * vy - uy * vx;
    const len = Math.hypot(nx, ny, nz) || 1;
    nx /= len; ny /= len; nz /= len;

    dv.setFloat32(off, nx, true); dv.setFloat32(off + 4, ny, true); dv.setFloat32(off + 8, nz, true);
    dv.setFloat32(off + 12, ax, true); dv.setFloat32(off + 16, ay, true); dv.setFloat32(off + 20, az, true);
    dv.setFloat32(off + 24, bx, true); dv.setFloat32(off + 28, by, true); dv.setFloat32(off + 32, bz, true);
    dv.setFloat32(off + 36, cx, true); dv.setFloat32(off + 40, cy, true); dv.setFloat32(off + 44, cz, true);
    dv.setUint16(off + 48, 0, true);  // attribute byte count
    off += 50;
  }
  return new Uint8Array(buf);
}
