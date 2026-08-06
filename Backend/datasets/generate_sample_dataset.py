"""
generate_sample_dataset.py

Gera um dataset SINTÉTICO de uma caminhada simulada, usado pelos testes
(tests/) e exemplos (examples/) enquanto não há um dataset real coletado
de um smartphone.

Simula ~10 segundos de caminhada a 50 Hz (500 amostras), com:
    - Az oscilando ao redor da gravidade (9.81 m/s²) com picos periódicos
      simulando o impacto de cada passo (~2 passos/segundo);
    - Gx, Gy, Gz com pequena oscilação simulando o balanço natural do
      corpo;
    - Mx, My, Mz aproximadamente constantes (campo magnético local
      estável), com um pequeno ruído;
    - Pressure levemente decrescente, simulando uma leve subida.

Não faz parte da arquitetura de produção do IndoorIPS — é apenas uma
ferramenta de apoio para gerar dados de teste reproduzíveis.
"""

from pathlib import Path

import numpy as np
import pandas as pd


def generate_walking_dataset(
    duration_s: float = 10.0,
    sample_rate_hz: float = 50.0,
    step_frequency_hz: float = 2.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Gera um DataFrame com colunas timestamp, ax..az, gx..gz, mx..mz, pressure."""
    rng = np.random.default_rng(seed)
    n_samples = int(duration_s * sample_rate_hz)
    t = np.arange(n_samples) / sample_rate_hz

    gravity = 9.81
    step_signal = 3.0 * np.sin(2 * np.pi * step_frequency_hz * t)
    noise_acc = rng.normal(0, 0.15, n_samples)

    ax = 0.3 * np.sin(2 * np.pi * step_frequency_hz * t + 0.5) + rng.normal(0, 0.1, n_samples)
    ay = 0.3 * np.cos(2 * np.pi * step_frequency_hz * t + 0.5) + rng.normal(0, 0.1, n_samples)
    az = gravity + step_signal + noise_acc

    gx = 0.05 * np.sin(2 * np.pi * step_frequency_hz * t) + rng.normal(0, 0.02, n_samples)
    gy = 0.05 * np.cos(2 * np.pi * step_frequency_hz * t) + rng.normal(0, 0.02, n_samples)
    gz = 0.02 * np.sin(2 * np.pi * 0.5 * t) + rng.normal(0, 0.02, n_samples)

    mx = 20.0 + rng.normal(0, 0.5, n_samples)
    my = -5.0 + rng.normal(0, 0.5, n_samples)
    mz = -40.0 + rng.normal(0, 0.5, n_samples)

    pressure = 1013.25 - 0.01 * t + rng.normal(0, 0.02, n_samples)

    return pd.DataFrame({
        "timestamp": t,
        "ax": ax, "ay": ay, "az": az,
        "gx": gx, "gy": gy, "gz": gz,
        "mx": mx, "my": my, "mz": mz,
        "pressure": pressure,
    })


if __name__ == "__main__":
    output_path = Path(__file__).parent / "sample_walk.csv"
    df = generate_walking_dataset()
    df.to_csv(output_path, index=False)
    print(f"Dataset sintético gerado: {output_path} ({len(df)} amostras)")
