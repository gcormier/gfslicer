"""End-to-end tests for the web endpoints via FastAPI's TestClient."""

import io

import pytest
import trimesh

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from gridfinity_slicer import core  # noqa: E402
from gridfinity_slicer.web import app  # noqa: E402

client = TestClient(app)


def bar_bytes(units_x: int = 3, fmt: str = "stl") -> bytes:
    length = units_x * core.GRID - 0.5
    box = trimesh.creation.box(extents=(length, 41.5, 21.0))
    box.apply_translation(-box.bounds[0])
    buf = io.BytesIO()
    box.export(buf, file_type=fmt)
    return buf.getvalue()


def test_inspect_reports_units():
    files = {"file": ("bar.stl", bar_bytes(3), "model/stl")}
    r = client.post("/inspect", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["units"] == {"x": 3, "y": 1}


def test_cut_downloads_smaller_mesh():
    files = {"file": ("bar.stl", bar_bytes(3), "model/stl")}
    data = {"axis": "x", "cell": "1", "count": "1", "out_format": "stl"}
    r = client.post("/cut", files=files, data=data)
    assert r.status_code == 200
    assert r.headers["content-disposition"].endswith('bar_cut_x1x1.stl"')
    result = trimesh.load(io.BytesIO(r.content), file_type="stl", force="mesh")
    span = result.bounds[1][0] - result.bounds[0][0]
    assert span == pytest.approx(2 * core.GRID - 0.5, abs=1e-3)


def test_cut_3mf_roundtrip():
    files = {"file": ("bar.3mf", bar_bytes(2, "3mf"), "model/3mf")}
    data = {"axis": "x", "cell": "0", "count": "1", "out_format": "3mf"}
    r = client.post("/cut", files=files, data=data)
    assert r.status_code == 200
    result = trimesh.load(io.BytesIO(r.content), file_type="3mf", force="mesh")
    assert not result.is_empty


def test_bad_axis_value_is_rejected():
    files = {"file": ("bar.stl", bar_bytes(2), "model/stl")}
    data = {"axis": "x", "cell": "5", "count": "1", "out_format": "stl"}
    r = client.post("/cut", files=files, data=data)
    assert r.status_code == 400


def test_unsupported_extension_rejected():
    files = {"file": ("bar.obj", b"junk", "text/plain")}
    r = client.post("/inspect", files=files)
    assert r.status_code == 400
