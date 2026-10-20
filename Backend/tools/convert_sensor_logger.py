"""Converte uma pasta exportada pelo Sensor Logger (Android) para o CSV das fixtures.

Entrada: TotalAcceleration.csv (m/s², COM gravidade) e Gyroscope.csv (rad/s),
colunas time(ns epoch),seconds_elapsed,z,y,x.

Saída: timestamp(s, relativo ao início),accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z.

Eixos: o Sensor Logger repassa o referencial do SensorManager do Android
(x direita, y topo, z para fora da tela), o mesmo do devicemotion do Chrome
para Android; com o celular deitado accel_z ≈ +9,8, como em
accelerationIncludingGravity. O giroscópio já vem em rad/s em x/y/z, que é o
que o recorder.js grava depois de converter beta/gamma/alpha de graus/s.
O giroscópio é interpolado na base de tempo do acelerômetro.

A partir de Backend/:

    python tools/convert_sensor_logger.py /caminho/gravacao tests/fixtures/walks/nome.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def convert(folder: Path) -> pd.DataFrame:
    acc = pd.read_csv(folder / "TotalAcceleration.csv").sort_values("time")
    gyr = pd.read_csv(folder / "Gyroscope.csv").sort_values("time")
    t0 = int(acc["time"].iloc[0])
    t_acc = (acc["time"].to_numpy(np.int64) - t0) / 1e9
    t_gyr = (gyr["time"].to_numpy(np.int64) - t0) / 1e9
    out = pd.DataFrame({"timestamp": t_acc})
    for axis in "xyz":
        out[f"accel_{axis}"] = acc[axis].to_numpy(float)
    for axis in "xyz":
        out[f"gyro_{axis}"] = np.interp(t_acc, t_gyr, gyr[axis].to_numpy(float))
    return out.drop_duplicates("timestamp").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    frame = convert(args.folder)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, float_format="%.6f")
    print(f"{args.output}: {len(frame)} amostras, {frame['timestamp'].iloc[-1]:.2f} s")


if __name__ == "__main__":
    main()
