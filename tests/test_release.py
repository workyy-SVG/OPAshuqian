import zipfile
from scripts.package_release import package_release


def test_release_contains_runnable_source_and_excludes_private_state(tmp_path):
    output = package_release(tmp_path)
    with zipfile.ZipFile(output) as bundle:
        names = set(bundle.namelist())
        assert {"qianpin/app.py", "qianpin/requirements-lock.txt", "qianpin/scripts/init_db.py",
                "qianpin/.streamlit/secrets.example.toml", "qianpin/README.md"} <= names
        assert 'qianpin/static/product-illustrations.png' in names
        assert not any("/runtime/" in p or "/.venv/" in p or p.endswith("/secrets.toml") or "/.git/" in p for p in names)
