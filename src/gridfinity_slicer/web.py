"""Minimal web UI for the GridFinity slicer.

Run with:  uv run gridfinity-slicer-web      (or: uv run uvicorn gridfinity_slicer.web:app)

Flow:
  1. POST /inspect  with an STL/3MF  -> grid dimensions + the mesh as STL for preview
  2. The browser shows a three.js preview and highlights the 42 mm slab to remove
  3. POST /cut      with the file + axis/cell/count -> downloads the rejoined mesh
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import trimesh
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response

from . import core

app = FastAPI(title="GridFinity Slicer")

_ALLOWED = {".stl", ".3mf"}


def _load_upload(data: bytes, filename: str) -> trimesh.Trimesh:
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(400, f"unsupported file type {suffix!r}; use .stl or .3mf")
    try:
        mesh = trimesh.load(io.BytesIO(data), file_type=suffix.lstrip("."), force="mesh")
    except Exception as exc:  # noqa: BLE001 - report any loader failure to the client
        raise HTTPException(400, f"could not parse mesh: {exc}") from exc
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise HTTPException(400, "file did not contain a usable mesh")
    return mesh


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.post("/inspect")
async def inspect_endpoint(file: UploadFile) -> dict:
    data = await file.read()
    mesh = _load_upload(data, file.filename or "upload")
    info = core.inspect(mesh)
    lo = mesh.bounds[0]
    size = info.size
    return {
        "filename": file.filename,
        "units": {"x": info.units[0], "y": info.units[1]},
        "size": {"x": float(size[0]), "y": float(size[1]), "z": float(size[2])},
        "min": {"x": float(lo[0]), "y": float(lo[1]), "z": float(lo[2])},
        "grid": core.GRID,
        "describe": info.describe(),
    }


@app.post("/cut")
async def cut_endpoint(
    file: UploadFile,
    axis: str = Form("x"),
    cell: int = Form(0),
    count: int = Form(1),
    out_format: str = Form("stl"),
    weld: bool = Form(True),
) -> Response:
    data = await file.read()
    mesh = _load_upload(data, file.filename or "upload")
    try:
        result = core.cut(mesh, axis=axis, cell=cell, count=count, weld=weld)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    fmt = out_format.lower()
    if fmt not in {"stl", "3mf"}:
        raise HTTPException(400, "out_format must be stl or 3mf")

    # trimesh exports 3mf/stl to a path or buffer depending on type; use a temp file
    # so 3mf (which writes a zip) works reliably.
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        result.export(tmp_path)
        payload = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    stem = Path(file.filename or "model").stem
    out_name = f"{stem}_cut_{axis}{cell}x{count}.{fmt}"
    media = "model/3mf" if fmt == "3mf" else "model/stl"
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


@app.post("/cutz")
async def cutz_endpoint(
    file: UploadFile,
    z_start: float = Form(...),
    z_end: float = Form(...),
    out_format: str = Form("stl"),
    weld: bool = Form(True),
) -> Response:
    data = await file.read()
    mesh = _load_upload(data, file.filename or "upload")
    try:
        result = core.cut_z(mesh, z_start=z_start, z_end=z_end, weld=weld)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    fmt = out_format.lower()
    if fmt not in {"stl", "3mf"}:
        raise HTTPException(400, "out_format must be stl or 3mf")

    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        result.export(tmp_path)
        payload = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    lo, hi = sorted((z_start, z_end))
    stem = Path(file.filename or "model").stem
    out_name = f"{stem}_cutz_{lo:g}-{hi:g}.{fmt}"
    media = "model/3mf" if fmt == "3mf" else "model/stl"
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


@app.post("/stretchz")
async def stretchz_endpoint(
    file: UploadFile,
    z_start: float = Form(...),
    z_end: float = Form(...),
    copies: int = Form(1),
    out_format: str = Form("stl"),
    weld: bool = Form(True),
) -> Response:
    data = await file.read()
    mesh = _load_upload(data, file.filename or "upload")
    try:
        result = core.stretch_z(mesh, z_start=z_start, z_end=z_end, copies=copies, weld=weld)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    fmt = out_format.lower()
    if fmt not in {"stl", "3mf"}:
        raise HTTPException(400, "out_format must be stl or 3mf")

    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        result.export(tmp_path)
        payload = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    lo, hi = sorted((z_start, z_end))
    stem = Path(file.filename or "model").stem
    out_name = f"{stem}_stretchz_{lo:g}-{hi:g}x{copies}.{fmt}"
    media = "model/3mf" if fmt == "3mf" else "model/stl"
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GridFinity Slicer</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font-family: system-ui, sans-serif; background:#15171c; color:#e6e6e6; }
  header { padding:14px 20px; background:#1d2027; border-bottom:1px solid #2c303a; }
  header h1 { margin:0; font-size:17px; font-weight:600; }
  header p { margin:4px 0 0; font-size:12px; color:#9aa0ac; }
  .wrap { display:flex; gap:16px; padding:16px; flex-wrap:wrap; }
  #viewport { flex:1 1 480px; min-height:460px; background:#0e1014; border:1px solid #2c303a; border-radius:8px; position:relative; }
  #hint { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#5b6270; font-size:13px; pointer-events:none; }
  .panel { flex:0 0 300px; display:flex; flex-direction:column; gap:14px; }
  .card { background:#1d2027; border:1px solid #2c303a; border-radius:8px; padding:14px; }
  .card h2 { margin:0 0 10px; font-size:13px; text-transform:uppercase; letter-spacing:.05em; color:#9aa0ac; }
  label { display:block; font-size:12px; margin:8px 0 4px; color:#b8bdc8; }
  input[type=file] { font-size:12px; }
  .row { display:flex; gap:8px; }
  .row > div { flex:1; }
  select, input[type=number] { width:100%; box-sizing:border-box; background:#0e1014; color:#e6e6e6;
    border:1px solid #353a45; border-radius:5px; padding:7px; font-size:13px; }
  button { width:100%; background:#3b82f6; color:#fff; border:0; border-radius:6px; padding:10px;
    font-size:14px; font-weight:600; cursor:pointer; margin-top:6px; }
  button:disabled { background:#33384a; color:#7a808c; cursor:not-allowed; }
  .seg { display:flex; gap:6px; }
  .seg button { flex:1; margin:0; background:#0e1014; border:1px solid #353a45; color:#cfd3db; font-weight:500; }
  .seg button.on { background:#3b82f6; border-color:#3b82f6; color:#fff; }
  pre { white-space:pre-wrap; font-size:11px; color:#9aa0ac; margin:0; line-height:1.5; }
  .err { color:#f87171; font-size:12px; }
  .legend { font-size:11px; color:#9aa0ac; display:flex; gap:14px; margin-top:8px; }
  .swatch { display:inline-block; width:11px; height:11px; border-radius:2px; vertical-align:middle; margin-right:5px; }
</style>
</head>
<body>
<header>
  <h1>GridFinity Slicer</h1>
  <p>Cut an exact 42&nbsp;mm chunk out of a bin and weld it back together.</p>
</header>
<div class="wrap">
  <div id="viewport"><div id="hint">Upload an STL or 3MF to preview</div></div>
  <div class="panel">
    <div class="card">
      <h2>1. File</h2>
      <input id="file" type="file" accept=".stl,.3mf">
      <pre id="info" style="margin-top:10px;"></pre>
      <div class="err" id="err"></div>
    </div>
    <div class="card">
      <h2>2. Cut</h2>
      <label>Axis</label>
      <div class="seg" id="axisSeg">
        <button data-axis="x" class="on">X</button>
        <button data-axis="y">Y</button>
        <button data-axis="z">Z</button>
      </div>
      <div id="xyInputs">
        <div class="row">
          <div>
            <label>First cell to remove</label>
            <input id="cell" type="number" min="0" value="0">
          </div>
          <div>
            <label>Number of cells</label>
            <input id="count" type="number" min="1" value="1">
          </div>
        </div>
      </div>
      <div id="zInputs" style="display:none;">
        <label>Operation</label>
        <div class="seg" id="zOpSeg">
          <button data-zop="remove" class="on">Remove</button>
          <button data-zop="stretch">Stretch</button>
        </div>
        <div class="row" style="margin-top:8px;">
          <div>
            <label>From Z (mm)</label>
            <input id="zStart" type="number" step="0.1" value="0">
          </div>
          <div>
            <label>To Z (mm)</label>
            <input id="zEnd" type="number" step="0.1" value="0">
          </div>
        </div>
        <label>Section size (Gridfinity 1U = 7 mm)</label>
        <div class="seg" id="zNudge">
          <button data-du="-7">&minus;1U</button>
          <button data-du="-3.5">&minus;&frac12;U</button>
          <button data-du="3.5">+&frac12;U</button>
          <button data-du="7">+1U</button>
        </div>
        <div id="zReadout" style="font-size:11px;color:#9aa0ac;margin-top:6px;"></div>
        <div id="zCopiesWrap" style="display:none;">
          <label>Copies to insert</label>
          <input id="zCopies" type="number" min="1" value="1">
        </div>
        <p id="zHint" style="font-size:11px;color:#9aa0ac;margin:8px 0 0;"></p>
      </div>
      <label>Output format</label>
      <select id="fmt"><option value="stl">STL</option><option value="3mf">3MF</option></select>
      <div class="legend">
        <span><span class="swatch" style="background:#9499a3"></span>keep</span>
        <span><span class="swatch" style="background:#f87171"></span>remove</span>
      </div>
      <button id="go" disabled>Cut &amp; download</button>
    </div>
  </div>
</div>

<script type="importmap">
{ "imports": {
  "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
  "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
} }
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { ThreeMFLoader } from 'three/addons/loaders/3MFLoader.js';

const GRID = 42.0;
const vp = document.getElementById('viewport');
const hint = document.getElementById('hint');
let renderer, scene, camera, controls, meshObj, slab, meta, fileData, fileName;
let axis = 'x';
let zop = 'remove';
const Z_UNIT = 7.0;

function initThree() {
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(devicePixelRatio);
  resize();
  vp.appendChild(renderer.domElement);
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1014);
  camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  controls = new OrbitControls(camera, renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x223044, 1.1));
  const d = new THREE.DirectionalLight(0xffffff, 1.4); d.position.set(1, 1.5, 1); scene.add(d);
  window.addEventListener('resize', resize);
  (function loop(){ requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); })();
}
function resize() {
  const w = vp.clientWidth, h = vp.clientHeight;
  if (renderer) { renderer.setSize(w, h, false); camera && (camera.aspect = w/h, camera.updateProjectionMatrix()); }
}

const previewMat = new THREE.MeshStandardMaterial({ color: 0x9499a3, metalness: 0.05, roughness: 0.85 });
const edgeMat = new THREE.LineBasicMaterial({ color: 0x202531 });

// Add a hard-edge wireframe overlay to a mesh so geometry reads clearly.
function addEdges(mesh) {
  const edges = new THREE.EdgesGeometry(mesh.geometry, 25); // angle threshold in degrees
  mesh.add(new THREE.LineSegments(edges, edgeMat));
}

function showMesh(arrayBuffer, isThreeMF) {
  if (meshObj) { scene.remove(meshObj); meshObj = null; }
  if (isThreeMF) {
    meshObj = new ThreeMFLoader().parse(arrayBuffer);
    meshObj.traverse(o => { if (o.isMesh) { o.material = previewMat; addEdges(o); } });
  } else {
    const geo = new STLLoader().parse(arrayBuffer);
    geo.computeVertexNormals();
    meshObj = new THREE.Mesh(geo, previewMat);
    addEdges(meshObj);
  }
  scene.add(meshObj);
  const bb = new THREE.Box3().setFromObject(meshObj);
  const c = new THREE.Vector3(); bb.getCenter(c);
  const size = new THREE.Vector3(); bb.getSize(size);
  const r = Math.max(size.x, size.y, size.z);
  controls.target.copy(c);
  camera.position.set(c.x + r*1.1, c.y + r*1.1, c.z + r*1.6);
  camera.near = r/100; camera.far = r*20; camera.updateProjectionMatrix();
  updateSlab();
}

function updateSlab() {
  if (slab) { scene.remove(slab); slab = null; }
  if (!meta) return;
  const min = meta.min, size = meta.size;
  const m = new THREE.MeshStandardMaterial({ color: 0xf87171, transparent: true, opacity: 0.5 });
  if (axis === 'z') {
    let z0 = +document.getElementById('zStart').value;
    let z1 = +document.getElementById('zEnd').value;
    if (z1 < z0) [z0, z1] = [z1, z0];
    const height = Math.max(0, z1 - z0);
    // teal section to duplicate when stretching, red slab to remove otherwise
    m.color.setHex(zop === 'stretch' ? 0x34d399 : 0xf87171);
    const g = new THREE.BoxGeometry(size.x * 1.02, size.y * 1.02, height || 1e-3);
    slab = new THREE.Mesh(g, m);
    slab.position.set(min.x + size.x/2, min.y + size.y/2, z0 + height/2);
    scene.add(slab);
    updateZReadout();
    return;
  }
  const cell = +document.getElementById('cell').value;
  const count = Math.max(1, +document.getElementById('count').value);
  const start = min[axis] + cell * GRID;
  const width = count * GRID;
  const g = new THREE.BoxGeometry(
    axis === 'x' ? width : size.x,
    axis === 'y' ? width : size.y,
    size.z * 1.02
  );
  slab = new THREE.Mesh(g, m);
  slab.position.set(
    axis === 'x' ? start + width/2 : min.x + size.x/2,
    axis === 'y' ? start + width/2 : min.y + size.y/2,
    min.z + size.z/2
  );
  scene.add(slab);
}

document.getElementById('file').addEventListener('change', async (e) => {
  const f = e.target.files[0]; if (!f) return;
  fileName = f.name;
  fileData = await f.arrayBuffer();
  const fd = new FormData(); fd.append('file', f);
  setErr('');
  let res;
  try { res = await fetch('/inspect', { method:'POST', body: fd }); }
  catch (err) { return setErr('upload failed: ' + err); }
  if (!res.ok) { return setErr((await res.json()).detail || 'inspect failed'); }
  const data = await res.json();
  meta = { min: data.min, size: data.size, units: data.units };
  document.getElementById('info').textContent = data.describe;
  document.getElementById('go').disabled = false;
  hint.style.display = 'none';
  try {
    showMesh(fileData.slice(0), fileName.toLowerCase().endsWith('.3mf'));
  } catch (err) {
    hint.textContent = 'preview unavailable — cut still works'; hint.style.display = 'flex';
  }
  clampInputs();
});

['cell','count','zStart','zEnd','zCopies'].forEach(id =>
  document.getElementById(id).addEventListener('input', () => { clampInputs(); updateSlab(); }));

document.querySelectorAll('#axisSeg button').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('#axisSeg button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); axis = b.dataset.axis;
    const z = axis === 'z';
    document.getElementById('xyInputs').style.display = z ? 'none' : '';
    document.getElementById('zInputs').style.display = z ? '' : 'none';
    document.getElementById('go').textContent =
      z && zop === 'stretch' ? 'Stretch & download' : 'Cut & download';
    if (z) initZDefaults();
    clampInputs(); updateSlab();
  }));

document.querySelectorAll('#zOpSeg button').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('#zOpSeg button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); zop = b.dataset.zop;
    document.getElementById('zCopiesWrap').style.display = zop === 'stretch' ? '' : 'none';
    document.getElementById('go').textContent = zop === 'stretch' ? 'Stretch & download' : 'Cut & download';
    clampInputs(); updateSlab();
  }));

// Section-size nudge buttons: grow/shrink the section by a Gridfinity unit.
document.querySelectorAll('#zNudge button').forEach(b =>
  b.addEventListener('click', () => {
    if (!meta) return;
    const zEl = document.getElementById('zStart'), zEl2 = document.getElementById('zEnd');
    let z0 = +zEl.value, z1 = +zEl2.value; if (z1 < z0) [z0, z1] = [z1, z0];
    z1 = z1 + parseFloat(b.dataset.du);
    zEl.value = z0.toFixed(2); zEl2.value = z1.toFixed(2);
    clampInputs(); updateSlab();
  }));

// Seed the Z fields with a sensible interior 1U section the first time Z is chosen.
function initZDefaults() {
  if (!meta) return;
  const zEl = document.getElementById('zStart'), zEl2 = document.getElementById('zEnd');
  if (+zEl.value === 0 && +zEl2.value === 0) {
    const lo = meta.min.z, h = meta.size.z;
    const start = lo + h/3;
    zEl.value = start.toFixed(2);
    zEl2.value = Math.min(start + Z_UNIT, lo + h).toFixed(2);
  }
}

function updateZReadout() {
  let z0 = +document.getElementById('zStart').value, z1 = +document.getElementById('zEnd').value;
  if (z1 < z0) [z0, z1] = [z1, z0];
  const h = Math.max(0, z1 - z0), u = h / Z_UNIT;
  const readout = document.getElementById('zReadout');
  const hint = document.getElementById('zHint');
  if (zop === 'stretch') {
    const n = Math.max(1, +document.getElementById('zCopies').value || 1);
    readout.textContent = `Section ${h.toFixed(2)} mm = ${u.toFixed(2)}U → +${(h*n).toFixed(2)} mm taller`;
    hint.textContent = 'Duplicates this section to make the model taller. Pick a section whose top and bottom cross-sections match (e.g. straight wall).';
  } else {
    readout.textContent = `Section ${h.toFixed(2)} mm = ${u.toFixed(2)}U (1U = 7 mm)`;
    hint.textContent = 'Removes everything between these two heights and welds the rest. Pick heights with matching cross-sections.';
  }
}

function clampInputs() {
  if (!meta) return;
  if (axis === 'z') {
    const lo = meta.min.z, hi = meta.min.z + meta.size.z;
    const zEl = document.getElementById('zStart'), zEl2 = document.getElementById('zEnd');
    zEl.min = lo.toFixed(2); zEl.max = hi.toFixed(2);
    zEl2.min = lo.toFixed(2); zEl2.max = hi.toFixed(2);
    zEl.value = Math.min(Math.max(lo, +zEl.value), hi);
    zEl2.value = Math.min(Math.max(lo, +zEl2.value), hi);
    const cEl = document.getElementById('zCopies');
    cEl.value = Math.max(1, Math.floor(+cEl.value) || 1);
    return;
  }
  const total = meta.units[axis];
  const countEl = document.getElementById('count'), cellEl = document.getElementById('cell');
  let count = Math.min(Math.max(1, +countEl.value), total);
  countEl.value = count; countEl.max = total;
  cellEl.max = Math.max(0, total - count);
  cellEl.value = Math.min(Math.max(0, +cellEl.value), total - count);
}

document.getElementById('go').addEventListener('click', async () => {
  if (!fileData) return;
  const fmt = document.getElementById('fmt').value;
  const fd = new FormData();
  fd.append('file', new Blob([fileData]), fileName);
  fd.append('out_format', fmt);
  let endpoint;
  if (axis === 'z') {
    fd.append('z_start', document.getElementById('zStart').value);
    fd.append('z_end', document.getElementById('zEnd').value);
    if (zop === 'stretch') {
      endpoint = '/stretchz';
      fd.append('copies', document.getElementById('zCopies').value);
    } else {
      endpoint = '/cutz';
    }
  } else {
    endpoint = '/cut';
    fd.append('axis', axis);
    fd.append('cell', document.getElementById('cell').value);
    fd.append('count', document.getElementById('count').value);
  }
  setErr('');
  const res = await fetch(endpoint, { method:'POST', body: fd });
  if (!res.ok) { return setErr((await res.json()).detail || 'cut failed'); }
  const blob = await res.blob();
  const dn = (res.headers.get('Content-Disposition')||'').match(/filename="(.+?)"/);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = dn ? dn[1] : 'cut.' + fmt;
  a.click(); URL.revokeObjectURL(a.href);
});

function setErr(m){ document.getElementById('err').textContent = m; }
initThree();
</script>
</body>
</html>
"""
