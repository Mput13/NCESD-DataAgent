"""Tests for parquet path resolution with env var fallback."""
import os
import shutil
import tempfile
from pathlib import Path

import pytest


class TestFedstatParquetPathEnvFallback:
    def test_finds_parquet_via_fedstat_dumps_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path must find file using FEDSTAT_DUMPS_DIR when catalog path is wrong."""
        # Create a real parquet file in a temp dumps dir
        dumps_dir = tmp_path / "fedstatru" / "data" / "parquet"
        dumps_dir.mkdir(parents=True)
        parquet_file = dumps_dir / "12345.parquet"
        parquet_file.write_bytes(b"fake parquet content")  # content doesn't matter for path test

        monkeypatch.setenv("FEDSTAT_DUMPS_DIR", str(dumps_dir))

        from app.data import fedstat_adapter
        # Reload to pick up env var (or call directly)
        import importlib
        importlib.reload(fedstat_adapter)

        source_card = {
            "dataset_id": "12345",
            "local_path": "/nonexistent/old/path/12345.parquet",  # wrong catalog path
        }

        from app.data.fedstat_adapter import _parquet_path
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_finds_parquet_by_dataset_id_in_dumps_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path finds file by dataset_id.parquet filename in FEDSTAT_DUMPS_DIR."""
        dumps_dir = tmp_path / "dumps"
        dumps_dir.mkdir()
        parquet_file = dumps_dir / "99999.parquet"
        parquet_file.write_bytes(b"fake")

        monkeypatch.setenv("FEDSTAT_DUMPS_DIR", str(dumps_dir))

        from app.data.fedstat_adapter import _parquet_path
        source_card = {"dataset_id": "99999"}
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_raises_when_dumps_dir_also_has_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path raises FileNotFoundError when env dir exists but file not there."""
        dumps_dir = tmp_path / "empty_dumps"
        dumps_dir.mkdir()

        monkeypatch.setenv("FEDSTAT_DUMPS_DIR", str(dumps_dir))

        from app.data.fedstat_adapter import _parquet_path
        source_card = {"dataset_id": "99999", "local_path": "/nonexistent/path.parquet"}

        with pytest.raises(FileNotFoundError):
            _parquet_path(source_card)

    def test_works_without_env_var_set(self, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path does not crash when FEDSTAT_DUMPS_DIR is not set."""
        monkeypatch.delenv("FEDSTAT_DUMPS_DIR", raising=False)

        from app.data.fedstat_adapter import _parquet_path
        source_card = {"dataset_id": "12345", "local_path": "/nonexistent/path.parquet"}

        with pytest.raises(FileNotFoundError):
            _parquet_path(source_card)  # should raise, not crash differently


class TestWorldBankParquetPathEnvFallback:
    def test_finds_parquet_via_world_bank_dumps_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path must find WB file using WORLD_BANK_DUMPS_DIR when catalog path is wrong."""
        dumps_dir = tmp_path / "wb_dumps"
        dumps_dir.mkdir()
        parquet_file = dumps_dir / "NY.GDP.MKTP.CD.parquet"
        parquet_file.write_bytes(b"fake parquet")

        monkeypatch.setenv("WORLD_BANK_DUMPS_DIR", str(dumps_dir))

        from app.data.world_bank_adapter import _parquet_path
        source_card = {
            "dataset_id": "NY.GDP.MKTP.CD",
            "local_path": "/nonexistent/old/path/NY.GDP.MKTP.CD.parquet",
        }
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_finds_by_card_id_filename(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path finds by card_id component ending in .parquet."""
        dumps_dir = tmp_path / "wb"
        dumps_dir.mkdir()
        parquet_file = dumps_dir / "SP.POP.TOTL.parquet"
        parquet_file.write_bytes(b"fake")

        monkeypatch.setenv("WORLD_BANK_DUMPS_DIR", str(dumps_dir))

        from app.data.world_bank_adapter import _parquet_path
        source_card = {
            "dataset_id": "SP.POP.TOTL",
            "card_id": "world_bank:SP.POP.TOTL:wb/parquet/SP.POP.TOTL.parquet",
        }
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_raises_when_not_found_anywhere(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setenv("WORLD_BANK_DUMPS_DIR", str(empty_dir))

        from app.data.world_bank_adapter import _parquet_path
        source_card = {"dataset_id": "NY.GDP.MKTP.CD"}

        with pytest.raises(FileNotFoundError):
            _parquet_path(source_card)
