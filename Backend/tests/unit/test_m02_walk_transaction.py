"""record_walk: uma transação, samples_count e caminhada inválida sem mexer na aresta."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from datasets.ManagerDatabase import ConexaoBD
from map.MapDatabaseManager import MapDatabaseManager

pytestmark = pytest.mark.unit


def _built(distance: float = 2.0) -> dict:
    return {
        "steps": [{
            "step_index": 0,
            "t_ms": 500,
            "heading_rad": 0.0,
            "step_length_m": distance,
            "x_m": distance,
            "y_m": 0.0,
        }],
        "polyline": [[0.0, 0.0], [distance, 0.0]],
        "total_distance_m": distance,
        "net_heading_rad": 0.0,
    }


class _TxDB:
    def __init__(self, fail_steps: bool = False) -> None:
        self.fail_steps = fail_steps
        self.open = False
        self.ops: list[str] = []
        self.traces: list[dict] = []
        self.steps: list = []
        self.edges: dict[tuple[str, str], dict] = {}
        self.next_trace = 1
        self.next_edge = 10
        self.edge_sql = ""
        self.searches: list[str] = []

    def _redact(self, exc):
        return ConexaoBD._redact(self, exc)

    def begin_transaction(self):
        self.open = True
        self.ops.append("begin")
        return True

    def commit_transaction(self):
        assert self.open
        self.open = False
        self.ops.append("commit")
        return True

    def rollback_transaction(self):
        self.open = False
        self.ops.append("rollback")
        self.traces.clear()
        self.steps.clear()
        return True

    def insert_within(self, sql, params=None):
        assert self.open
        self.ops.append("insert")
        if "INSERT INTO walk_traces" in sql:
            trace_id = self.next_trace
            self.next_trace += 1
            self.traces.append({
                "id": trace_id,
                "source_node": params[1],
                "target_node": params[2],
                "started_at": params[3],
                "total_steps": params[5],
                "total_distance_m": params[6],
                "net_heading_rad": params[7],
                "is_valid": params[9],
            })
            return trace_id
        if "INSERT INTO edges" in sql:
            self.edge_sql = sql
            key = (params[0], params[1])
            current = self.edges.get(key)
            if current is None:
                current = {"id": self.next_edge, "source_node": params[0], "target_node": params[1]}
                self.next_edge += 1
                self.edges[key] = current
                current["distance_m"] = params[2]
                current["heading_rad"] = params[3]
                current["origin"] = params[4]
            elif current["origin"] != "manual":
                current["distance_m"] = params[2]
                current["heading_rad"] = params[3]
                current["origin"] = params[4]
            current["active_trace_id"] = params[5]
            current["samples_count"] = params[6]
            return current["id"]
        return None

    def executemany_within(self, sql, seq):
        assert self.open
        if self.fail_steps:
            return False
        self.steps.extend(list(seq))
        self.ops.append("steps")
        return True

    def execute_within(self, sql, params=None):
        assert self.open
        self.ops.append("update")
        return True

    def _valid(self, params):
        return [
            row for row in self.traces
            if row["source_node"] == params[0]
            and row["target_node"] == params[1]
            and row["is_valid"] == 1
        ]

    def execute_search(self, sql, params=None):
        params = params or ()
        self.searches.append(sql)
        if "AS samples_count" in sql:
            valid = self._valid(params)
            if not valid:
                return [{"samples_count": 0, "heading_rad": None}]
            from map.edge_rules import circular_mean
            return [{
                "samples_count": len(valid),
                "heading_rad": circular_mean([
                    float(row["net_heading_rad"] or 0) for row in valid
                ]),
            }]
        if "ORDER BY total_distance_m" in sql:
            import re
            match = re.search(r"LIMIT (\d+) OFFSET (\d+)", sql)
            limit, offset = int(match.group(1)), int(match.group(2))
            ordered = sorted(self._valid(params), key=lambda row: float(row["total_distance_m"]))
            return [
                {"total_distance_m": row["total_distance_m"]}
                for row in ordered[offset:offset + limit]
            ]
        if "ORDER BY started_at DESC" in sql:
            valid = self._valid(params)
            if not valid:
                return []
            latest = max(valid, key=lambda row: (str(row["started_at"]), int(row["id"])))
            return [{"id": latest["id"]}]
        if "FROM walk_traces" in sql:
            return self._valid(params)
        if "FROM edges" in sql:
            found = self.edges.get((params[0], params[1]))
            return [found] if found else []
        return []


def test_valid_walk_commits_once_and_counts_sample():
    db = _TxDB()
    started = "2026-10-20 16:05:11.020"
    saved = MapDatabaseManager(db).record_walk(
        "Quarto", "Sala", 4, started, started, _built(2.0), is_valid=True,
    )
    assert saved is not None
    assert db.ops[0] == "begin"
    assert db.ops[-1] == "commit"
    assert "rollback" not in db.ops
    assert saved["trace_id"] == 1
    assert saved["samples_count"] == 1
    assert saved["edge_origin"] == "recorded"
    assert saved["edge_distance_m"] == pytest.approx(2.0)
    assert "samples_count" in db.edge_sql
    assert "dup_rank" in db.edge_sql
    assert ", 0)" in db.edge_sql
    expected_t = datetime(2026, 10, 20, 16, 5, 11, 20000, tzinfo=timezone.utc).timestamp()
    assert saved["path"][0] == {"x": 0.0, "y": 0.0, "t": pytest.approx(expected_t)}
    assert len(saved["path"]) == 2
    assert set(saved["path"][1]) == {"x", "y", "t"}
    assert db.edges[("Quarto", "Sala")]["samples_count"] == 1


def test_manual_edge_keeps_distance_and_still_counts():
    db = _TxDB()
    db.edges[("Quarto", "Sala")] = {
        "id": 5,
        "source_node": "Quarto",
        "target_node": "Sala",
        "distance_m": 3.0,
        "heading_rad": 1.0,
        "origin": "manual",
        "samples_count": 0,
        "active_trace_id": None,
    }
    saved = MapDatabaseManager(db).record_walk(
        "Quarto", "Sala", 4, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
        _built(2.0), is_valid=True,
    )
    assert saved["edge_origin"] == "manual"
    assert saved["edge_distance_m"] == pytest.approx(3.0)
    assert saved["edge_heading_rad"] == pytest.approx(1.0)
    assert saved["samples_count"] == 1
    assert db.edges[("Quarto", "Sala")]["samples_count"] == 1
    assert db.edges[("Quarto", "Sala")]["distance_m"] == 3.0


def test_invalid_walk_does_not_change_the_edge():
    db = _TxDB()
    db.edges[("Quarto", "Sala")] = {
        "id": 5,
        "source_node": "Quarto",
        "target_node": "Sala",
        "distance_m": 3.0,
        "heading_rad": 1.0,
        "origin": "manual",
        "samples_count": 0,
        "active_trace_id": None,
    }
    saved = MapDatabaseManager(db).record_walk(
        "Quarto", "Sala", 4, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
        _built(2.0), is_valid=False,
    )
    assert saved["trace_id"] == 1
    assert saved["is_valid"] is False
    assert saved["edge_id"] == 5
    assert saved["edge_distance_m"] == pytest.approx(3.0)
    assert db.edges[("Quarto", "Sala")]["samples_count"] == 0
    assert db.edges[("Quarto", "Sala")]["active_trace_id"] is None
    assert db.traces[0]["is_valid"] == 0
    assert "INSERT INTO edges" not in db.edge_sql
    assert db.ops[-1] == "commit"


def test_median_uses_the_middle_distance_not_the_latest():
    db = _TxDB()
    manager = MapDatabaseManager(db)
    stamps = (
        "2026-10-20 16:05:11.020",
        "2026-10-20 16:05:12.020",
        "2026-10-20 16:05:13.020",
    )
    saved = None
    for stamp, distance in zip(stamps, (1.0, 100.0, 10.0)):
        saved = manager.record_walk(
            "Quarto", "Sala", 4, stamp, stamp, _built(distance), is_valid=True,
        )
        assert saved is not None
    assert saved["samples_count"] == 3
    assert saved["edge_distance_m"] == pytest.approx(10.0)
    assert saved["edge_origin"] == "recorded"
    assert db.edges[("Quarto", "Sala")]["samples_count"] == 3
    assert any("ORDER BY total_distance_m" in sql for sql in db.searches)
    assert not any("polyline_json" in sql and "is_valid = 1" in sql for sql in db.searches)


def test_save_edge_commits_both_directions_in_name_order():
    db = _EdgeTx()
    manager = MapDatabaseManager(db)
    assert manager.save_edge("Sala", "Quarto", 4.0, 0.2) is True
    assert db.ops[0] == "begin"
    assert db.ops[-1] == "commit"
    assert db.ops.count("commit") == 1
    assert [pair for pair in db.order] == [("Quarto", "Sala"), ("Sala", "Quarto")]
    assert db.edges[("Sala", "Quarto")][2] == pytest.approx(4.0)
    assert db.edges[("Quarto", "Sala")][3] == pytest.approx((0.2 + math.pi) % (2 * math.pi))

    again = _EdgeTx()
    assert MapDatabaseManager(again).save_edge("Quarto", "Sala", 4.0, 1.0) is True
    assert [pair for pair in again.order] == [("Quarto", "Sala"), ("Sala", "Quarto")]


def test_save_edge_rollback_redacts_the_password_and_the_url(capsys):
    secret = "senha12"
    db = _EdgeTx()
    db.password = secret

    def execute_within(sql, params=None):
        raise RuntimeError(f"mysql://pov:{secret}@127.0.0.1:3306/POV {secret}")

    db.execute_within = execute_within
    assert MapDatabaseManager(db).save_edge("Sala", "Quarto", 4.0, 0.2) is False
    assert "rollback" in db.ops
    printed = capsys.readouterr().out
    assert printed.startswith("Aresta revertida:")
    assert secret not in printed
    assert "pov:" not in printed
    assert "mysql://***@127.0.0.1:3306/POV" in printed


def test_save_edge_masks_a_short_password_inside_the_url(capsys):
    db = _EdgeTx()
    db.password = "ab"

    def execute_within(sql, params=None):
        raise RuntimeError("mysql://pov:ab@127.0.0.1/POV")

    db.execute_within = execute_within
    assert MapDatabaseManager(db).save_edge("Sala", "Quarto", 4.0, 0.2) is False
    printed = capsys.readouterr().out
    assert "pov:ab@" not in printed
    assert "ab" not in printed
    assert "mysql://***@127.0.0.1/POV" in printed


def test_walk_rollback_redacts_the_password_and_the_url(capsys):
    secret = "senha12"
    db = _TxDB()
    db.password = secret

    def insert_within(sql, params=None):
        raise RuntimeError(f"mysql://root:{secret}@10.0.0.5/POV {secret}")

    db.insert_within = insert_within
    saved = MapDatabaseManager(db).record_walk(
        "Quarto", "Sala", 4, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
        _built(), is_valid=True,
    )
    assert saved is None
    assert "rollback" in db.ops
    printed = capsys.readouterr().out
    assert printed.startswith("Trajetória revertida:")
    assert secret not in printed
    assert "root:" not in printed
    assert "mysql://***@10.0.0.5/POV" in printed


def test_save_edge_rolls_back_when_the_second_direction_fails():
    db = _EdgeTx(fail_second=True)
    assert MapDatabaseManager(db).save_edge("Sala", "Quarto", 4.0, 0.2) is False
    assert "commit" not in db.ops
    assert "rollback" in db.ops
    assert db.edges == {}


class _EdgeTx:
    def __init__(self, fail_second: bool = False) -> None:
        self.fail_second = fail_second
        self.ops: list[str] = []
        self.order: list[tuple[str, str]] = []
        self.edges: dict[tuple[str, str], tuple] = {}
        self.open = False
        self.upserts = 0

    def _redact(self, exc):
        return ConexaoBD._redact(self, exc)

    def begin_transaction(self):
        self.open = True
        self.ops.append("begin")
        return True

    def commit_transaction(self):
        assert self.open
        self.open = False
        self.ops.append("commit")
        return True

    def rollback_transaction(self):
        self.open = False
        self.edges.clear()
        self.order.clear()
        self.ops.append("rollback")
        return True

    def execute_search(self, sql, params=None):
        self.ops.append("lock")
        return []

    def execute_within(self, sql, params=None):
        assert self.open
        self.upserts += 1
        if self.fail_second and self.upserts == 2:
            return False
        self.order.append((params[0], params[1]))
        self.edges[(params[0], params[1])] = params
        return True


def test_step_failure_rolls_back_and_skips_the_edge():
    db = _TxDB(fail_steps=True)
    saved = MapDatabaseManager(db).record_walk(
        "Quarto", "Sala", 4, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
        _built(), is_valid=True,
    )
    assert saved is None
    assert "commit" not in db.ops
    assert "rollback" in db.ops
    assert db.traces == []
    assert db.edges == {}
