"""Reproduz o travamento do salvamento e confere que a gravação nova não espera.

Uso (com o MySQL do XAMPP ou outro local já criado):

    cd Backend
    set DB_HOST=127.0.0.1
    set DB_USER=pov
    set DB_PASSWORD=
    set DB_NAME=pov_save_repro
    python -m datasets.repro_save_hang

O banco precisa existir e o usuário precisa poder criar tabelas nele.
DB_USER e DB_PASSWORD são obrigatórios. Não há conta root no script.
POV_DB_HOST, POV_DB_USER, POV_DB_PASSWORD e POV_DB_NAME ainda valem se
as DB_* correspondentes não estiverem definidas.
O script aplica as migrações do projeto (create_tables) e no final apaga
as linhas que ele mesmo gravou. Não mexe em outro schema.

O que ele prova:
- o padrão antigo (INSERT filho sem commit) faz o UPDATE do checkpoint
  esperar o tempo inteiro da transação;
- os dois sentidos da aresta, cada transação começando pelo seu source,
  recebem deadlock 1213;
- save_edge e record_walk, na ordem nova, terminam sem espera de lock
  e sem transação aberta.
"""

from __future__ import annotations

import os
import sys
import threading
import time

import mysql.connector

from datasets.ManagerDatabase import ConexaoBD
from datasets.create_tables import criar_tabelas_sistema
from map.MapDatabaseManager import MapDatabaseManager
from map.edge_rules import circular_mean, median


def _setting(name: str, legacy: str) -> str:
    if name in os.environ:
        return os.environ[name]
    if legacy in os.environ:
        return os.environ[legacy]
    raise SystemExit(
        f"Falta {name}. Este script não assume root. "
        "Defina DB_HOST, DB_USER, DB_PASSWORD e DB_NAME "
        "(ou os nomes antigos POV_DB_*)."
    )


def _connect(database: str | None = None, autocommit: bool = True):
    kwargs = dict(
        host=_setting("DB_HOST", "POV_DB_HOST"),
        user=_setting("DB_USER", "POV_DB_USER"),
        password=_setting("DB_PASSWORD", "POV_DB_PASSWORD"),
        autocommit=autocommit,
    )
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def _db_name() -> str:
    if "DB_NAME" in os.environ or "POV_DB_NAME" in os.environ:
        return _setting("DB_NAME", "POV_DB_NAME")
    return "pov_save_repro"


def _app() -> tuple[ConexaoBD, MapDatabaseManager]:
    db = ConexaoBD(
        _setting("DB_HOST", "POV_DB_HOST"),
        _db_name(),
        _setting("DB_USER", "POV_DB_USER"),
        _setting("DB_PASSWORD", "POV_DB_PASSWORD"),
    )
    db.connect(announce=False)
    if not db.connection:
        raise SystemExit(
            "Não conectou. Confira DB_HOST, DB_USER e DB_PASSWORD. "
            "O script não entra como root."
        )
    return db, MapDatabaseManager(db)


def _wipe(cur) -> None:
    for table in ("walk_steps", "edges", "walk_traces", "sensors_log", "saved_routes", "checkpoints"):
        cur.execute(f"DELETE FROM {table}")


def _seed_pair(cur) -> int:
    cur.execute(
        "INSERT INTO checkpoints (name, building_id, slug) VALUES "
        "('Sala', 1, 'sala'), ('Quarto', 1, 'quarto'), ('Copa', 1, 'copa')"
    )
    cur.execute(
        "INSERT INTO sensors_log (source, target, raw_csv, is_valid) VALUES ('Sala', 'Quarto', 'x', 1)"
    )
    return int(cur.lastrowid)


def _built(distance: float, heading: float = 0.0) -> dict:
    return {
        "steps": [{
            "step_index": 0,
            "t_ms": 400,
            "heading_rad": heading,
            "step_length_m": distance,
            "x_m": distance,
            "y_m": 0.0,
        }],
        "polyline": [[0.0, 0.0], [distance, 0.0]],
        "total_distance_m": distance,
        "net_heading_rad": heading,
    }


def demonstrate_old_lock_wait(cur_factory) -> None:
    """INSERT do trace sem commit segura S lock no checkpoint. O UPDATE espera."""
    holder = cur_factory(False)
    waiter = cur_factory(False)
    hc, wc = holder.cursor(), waiter.cursor()
    hc.execute("SELECT id FROM sensors_log LIMIT 1")
    log_id = hc.fetchall()[0][0]
    hc.execute(
        """
        INSERT INTO walk_traces (
            sensors_log_id, edge_id, source_node, target_node,
            started_at, ended_at, total_steps, total_distance_m, net_heading_rad, is_valid
        ) VALUES (%s, NULL, 'Sala', 'Quarto', NOW(3), NOW(3), 1, 2, 0, 1)
        """,
        (log_id,),
    )
    elapsed: dict[str, float] = {}

    def update_position():
        wc.execute("SET SESSION innodb_lock_wait_timeout = 5")
        started = time.perf_counter()
        wc.execute("UPDATE checkpoints SET pos_x_px = 12 WHERE name = 'Sala'")
        waiter.commit()
        elapsed["update"] = time.perf_counter() - started

    thread = threading.Thread(target=update_position)
    thread.start()
    time.sleep(1.0)
    holder.commit()
    thread.join(timeout=8)
    holder.close()
    waiter.close()
    if thread.is_alive():
        raise SystemExit("O UPDATE antigo não soltou. O script ia ficar preso.")
    print(f"[causa] UPDATE do checkpoint esperou {elapsed['update']:.3f}s a transação do trace")
    if elapsed["update"] < 0.8:
        raise SystemExit("Esperava o UPDATE bloquear enquanto o trace estava aberto.")


def demonstrate_old_deadlock(cur_factory) -> None:
    """Cada transação grava o próprio sentido primeiro. O segundo INSERT deadloca."""
    results: dict[str, str] = {}
    go = threading.Event()

    def session(name: str, first: tuple[str, str], second: tuple[str, str]) -> None:
        cn = cur_factory(False)
        cu = cn.cursor()
        try:
            cu.execute("SET SESSION innodb_lock_wait_timeout = 3")
            cu.execute("START TRANSACTION")
            cu.execute(
                """
                INSERT INTO edges (source_node, target_node, distance_m, heading_rad, origin)
                VALUES (%s, %s, 1, 0, 'manual')
                """,
                first,
            )
            go.wait(5)
            cu.execute(
                """
                INSERT INTO edges (source_node, target_node, distance_m, heading_rad, origin)
                VALUES (%s, %s, 1, 1, 'manual')
                """,
                second,
            )
            cn.commit()
            results[name] = "ok"
        except Exception as exc:
            results[name] = str(exc)
            try:
                cn.rollback()
            except Exception:
                pass
        finally:
            cn.close()

    left = threading.Thread(target=session, args=("ab", ("Sala", "Quarto"), ("Quarto", "Sala")))
    right = threading.Thread(target=session, args=("ba", ("Quarto", "Sala"), ("Sala", "Quarto")))
    left.start()
    right.start()
    time.sleep(0.3)
    go.set()
    left.join(timeout=8)
    right.join(timeout=8)
    print("[causa] sentidos cruzados:", results)
    text = " ".join(results.values())
    if "1213" not in text and "Deadlock" not in text:
        raise SystemExit("Esperava deadlock 1213 ao gravar os dois sentidos sem ordem fixa.")
    cleanup = cur_factory(True)
    cleanup.cursor().execute("DELETE FROM edges")
    cleanup.commit()
    cleanup.close()


def _open_transactions(cur) -> list:
    cur.execute(
        "SELECT trx_id, trx_state FROM information_schema.innodb_trx"
    )
    return list(cur.fetchall())


def _thread_manager() -> tuple[ConexaoBD, MapDatabaseManager]:
    local, local_manager = _app()
    return local, local_manager


def exercise_fixed_saves(db: ConexaoBD, manager: MapDatabaseManager) -> None:
    _wipe(db.cursor)
    _seed_pair(db.cursor)
    cur = db.cursor
    # MariaDB 10.11 expõe tx_isolation. MySQL 8 expõe transaction_isolation.
    iso_var = "transaction_isolation"
    cur.execute("SHOW VARIABLES LIKE '%isolation%'")
    names = {next(iter(row.values())) for row in cur.fetchall()}
    if "transaction_isolation" not in names and "tx_isolation" in names:
        iso_var = "tx_isolation"
    cur.execute(
        f"SELECT @@{iso_var} AS iso, @@innodb_lock_wait_timeout AS wait_s, @@autocommit AS ac"
    )
    session = cur.fetchall()[0]
    print("[sessão]", session)
    if "READ-COMMITTED" not in str(session["iso"]).upper().replace(" ", "-"):
        raise SystemExit(f"Isolamento da sessão não é READ COMMITTED: {session}")
    if int(session["wait_s"]) > 5:
        raise SystemExit("innodb_lock_wait_timeout da sessão passou de 5s; o save volta a parecer travado.")
    if int(session["ac"]) != 1:
        raise SystemExit("autocommit da sessão não está ligado.")

    assert manager.save_checkpoint("Hall")["slug"] == "hall"
    assert manager.update_checkpoint_position("Hall", 10, 20) is True
    assert manager.update_checkpoint_position("Hall", 10, 20) is True

    errors: list[str] = []

    def save(source: str, target: str) -> None:
        local = None
        try:
            local, local_manager = _thread_manager()
            if not local_manager.save_edge(source, target, 3.5, 0.4):
                errors.append(f"save_edge {source}->{target} devolveu falso")
        except Exception as exc:
            errors.append(str(exc))
        finally:
            if local is not None:
                local.disconnect(announce=False)

    threads = []
    for _ in range(12):
        threads.append(threading.Thread(target=save, args=("Sala", "Quarto")))
        threads.append(threading.Thread(target=save, args=("Quarto", "Sala")))
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)
        if thread.is_alive():
            raise SystemExit("save_edge não terminou em 8s.")
    elapsed = time.perf_counter() - started
    print(f"[save_edge] 24 gravações cruzadas em {elapsed:.3f}s")
    if errors:
        raise SystemExit("save_edge falhou: " + "; ".join(errors[:5]))
    if elapsed > 5:
        raise SystemExit("save_edge concorrente passou de 5s.")
    cur.execute(
        "SELECT source_node, target_node, origin FROM edges WHERE source_node IN ('Sala', 'Quarto')"
    )
    directions = {(row["source_node"], row["target_node"]) for row in cur.fetchall()}
    if directions != {("Sala", "Quarto"), ("Quarto", "Sala")}:
        raise SystemExit(f"Ficou aresta pela metade: {directions}")
    # O teste acima grava origin='manual'. A mediana só substitui aresta gravada.
    cur.execute("DELETE FROM edges")

    log_id = manager.save_sensor_log("Sala", "Quarto", "amostra")
    if not log_id:
        raise SystemExit("Não gravou sensors_log.")
    distances = (1.0, 10.0, 4.0)
    headings = (0.0, 1.2, -0.4)
    saved = None
    for index, (distance, heading) in enumerate(zip(distances, headings)):
        stamp = f"2026-10-20 16:05:1{index}.020"
        saved = manager.record_walk(
            "Sala", "Quarto", int(log_id), stamp, stamp, _built(distance, heading), True,
        )
        if not saved:
            raise SystemExit("record_walk devolveu vazio.")
    assert saved is not None
    expected_distance = median(list(distances))
    expected_heading = circular_mean(list(headings))
    print(
        "[record_walk] mediana",
        saved["edge_distance_m"],
        "esperada",
        expected_distance,
        "heading",
        saved["edge_heading_rad"],
    )
    if abs(float(saved["edge_distance_m"]) - expected_distance) > 1e-6:
        raise SystemExit("A distância gravada não é a mediana.")
    if abs(float(saved["edge_heading_rad"]) - expected_heading) > 1e-6:
        raise SystemExit("O heading gravado não é a média circular.")
    if int(saved["samples_count"]) != 3:
        raise SystemExit(f"samples_count {saved['samples_count']} != 3")

    # Aresta manual não perde a distância quando entra uma caminhada.
    assert manager.save_edge("Copa", "Sala", 8.0, 0.3) is True
    manual = manager.record_walk(
        "Copa", "Sala", int(log_id),
        "2026-10-20 16:06:00.000", "2026-10-20 16:06:01.000",
        _built(2.0, 0.9), True,
    )
    if not manual or abs(float(manual["edge_distance_m"]) - 8.0) > 1e-6:
        raise SystemExit(f"Aresta manual foi sobrescrita: {manual}")
    if manual["edge_origin"] != "manual":
        raise SystemExit("origin manual não foi preservada.")

    calls: list[str] = []
    original = db.execute_search

    def counted(sql, params=None):
        calls.append(sql)
        return original(sql, params)

    db.execute_search = counted
    listed = manager.list_connections(include_path=True)
    db.execute_search = original
    if not listed:
        raise SystemExit("list_connections veio vazio.")
    trace_queries = [sql for sql in calls if "FROM walk_traces" in sql]
    step_queries = [sql for sql in calls if "FROM walk_steps" in sql]
    edge_queries = [sql for sql in calls if "FROM edges" in sql]
    print(
        "[list_connections]",
        len(listed),
        "pares,",
        len(edge_queries),
        "SELECT edges,",
        len(trace_queries),
        "SELECT traces,",
        len(step_queries),
        "SELECT steps",
    )
    if len(edge_queries) != 1 or len(trace_queries) != 1 or len(step_queries) != 1:
        raise SystemExit("list_connections voltou a consultar uma vez por aresta.")

    cur.execute(
        """
        EXPLAIN SELECT COUNT(*) FROM walk_traces
        WHERE source_node = 'Sala' AND target_node = 'Quarto' AND is_valid = 1
        """
    )
    plan = cur.fetchall()[0]
    print("[EXPLAIN agregação]", plan.get("key"), plan.get("type"), plan.get("Extra"))
    if plan.get("type") == "ALL":
        raise SystemExit("A agregação da aresta fez varredura da tabela.")
    if plan.get("key") not in ("idx_trace_median", "idx_trace_latest", "idx_trace_pair"):
        raise SystemExit(f"A agregação não usou o índice do par: {plan.get('key')}")

    open_trx = _open_transactions(cur)
    print("[innodb_trx depois dos saves]", open_trx)
    if open_trx:
        raise SystemExit("Ficou transação aberta depois de salvar.")

    # Posição e caminhada ao mesmo tempo: não pode passar do timeout de 5s.
    position_done = threading.Event()

    def move_sala():
        local = ConexaoBD(db.host, db.database, db.user, db.password)
        local.connect(announce=False)
        local_manager = MapDatabaseManager(local)
        for value in range(20):
            if not local_manager.update_checkpoint_position("Sala", float(value), 1.0):
                errors.append("posição não gravou")
                break
        local.disconnect(announce=False)
        position_done.set()

    mover = threading.Thread(target=move_sala)
    walk_started = time.perf_counter()
    mover.start()
    for index in range(8):
        stamp = f"2026-10-20 17:00:0{index}.000"
        walked = manager.record_walk(
            "Sala", "Quarto", int(log_id), stamp, stamp, _built(3.0, 0.1), True,
        )
        if not walked:
            raise SystemExit("record_walk concorrente com a posição falhou.")
    mover.join(timeout=8)
    both = time.perf_counter() - walk_started
    print(f"[concorrente] posição + caminhadas em {both:.3f}s")
    if mover.is_alive() or not position_done.is_set():
        raise SystemExit("Salvar a posição travou enquanto a caminhada gravava.")
    if both > 5:
        raise SystemExit("Salvar posição e caminhada juntos passou de 5s.")
    if errors:
        raise SystemExit("Falhou no meio da concorrência: " + "; ".join(errors[:5]))
    if _open_transactions(cur):
        raise SystemExit("Transação aberta depois da gravação concorrente.")


def main() -> None:
    name = _db_name()
    probe = _connect()
    probe.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4")
    probe.close()

    db, manager = _app()
    criar_tabelas_sistema(db)
    cur = db.cursor
    cur.execute(
        """
        SELECT index_name FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = 'walk_traces'
          AND index_name IN ('idx_trace_median', 'idx_trace_latest')
        GROUP BY index_name
        """
    )
    found = {row["index_name"] for row in cur.fetchall()}
    print("[índices]", sorted(found))
    if found != {"idx_trace_median", "idx_trace_latest"}:
        raise SystemExit(f"Migração 004 não deixou os dois índices: {found}")

    _wipe(cur)
    _seed_pair(cur)

    def factory(autocommit: bool):
        return _connect(name, autocommit=autocommit)

    demonstrate_old_lock_wait(factory)
    demonstrate_old_deadlock(factory)
    exercise_fixed_saves(db, manager)
    _wipe(cur)
    db.disconnect(announce=False)
    print("OK: salvamento reproduzido sem travar.")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
