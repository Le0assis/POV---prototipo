"""
test_filters.py

Testes unitários da Etapa 3 (Filtragem de Sinais) e Etapa 7/8 (Quaternions e Fusão).
Garante que os filtros não distorçam sinais e que a matemática 3D esteja correta.

Como rodar:
    python -m unittest tests.test_filters -v
"""

import unittest
import numpy as np
from filters.butterworth import ButterworthLowPassFilter
from filters.moving_average import MovingAverageFilter
from filters.quaternion import Quaternion
from filters.madgwick import MadgwickAttitudeEstimator


class TestButterworthFilter(unittest.TestCase):
    """Testes do Filtro Butterworth Passa-Baixa."""

    def setUp(self) -> None:
        self.sample_rate = 100.0  # 100 Hz
        self.cutoff = 3.0         # 3 Hz (caminhada)
        self.filter = ButterworthLowPassFilter(self.cutoff, self.sample_rate, order=4)

    def test_rejects_cutoff_above_nyquist(self) -> None:
        """O filtro deve estourar erro se a frequência de corte violar Nyquist."""
        invalid_cutoff = self.sample_rate / 2.0  # Igual ou maior que Nyquist (50Hz)
        with self.assertRaises(ValueError):
            ButterworthLowPassFilter(invalid_cutoff, self.sample_rate)

    def test_rejects_short_signal(self) -> None:
        """O filtfilt exige um tamanho mínimo de sinal baseado na ordem do filtro."""
        short_signal = np.array([1.0, 2.0, 3.0])
        with self.assertRaises(ValueError):
            self.filter.apply(short_signal)

    def test_attenuates_high_frequency_noise(self) -> None:
        """Garante que o ruído de alta frequência seja severamente atenuado."""
        t = np.linspace(0, 1, int(self.sample_rate), endpoint=False)
        
        # Sinal limpo (1 Hz - banda de passagem) + Ruído forte (40 Hz - banda de rejeição)
        clean_signal = np.sin(2 * np.pi * 1.0 * t)
        noise = 0.5 * np.sin(2 * np.pi * 40.0 * t)
        noisy_signal = clean_signal + noise

        filtered = self.filter.apply(noisy_signal)

        # O sinal filtrado deve ser muito mais próximo do limpo do que do ruidoso
        rmse_before = np.sqrt(np.mean((noisy_signal - clean_signal) ** 2))
        rmse_after = np.sqrt(np.mean((filtered - clean_signal) ** 2))

        self.assertTrue(rmse_after < rmse_before)
        self.assertAlmostEqual(filtered[50], clean_signal[50], places=1)


class TestMovingAverageFilter(unittest.TestCase):
    """Testes do Filtro de Média Móvel."""

    def test_rejects_invalid_window_size(self) -> None:
        """Janela deve ser maior ou igual a 1."""
        with self.assertRaises(ValueError):
            MovingAverageFilter(window_size=0)

    def test_rejects_signal_smaller_than_window(self) -> None:
        """Sinal menor que a janela deve disparar erro."""
        filt = MovingAverageFilter(window_size=11)
        short_signal = np.ones(5)
        with self.assertRaises(ValueError):
            filt.apply(short_signal)

    def test_smooths_out_spike(self) -> None:
        """Um spike isolado deve ser suavizado pela média móvel."""
        filt = MovingAverageFilter(window_size=3)
        # Um sinal constante com um pico bizarro no meio
        signal = np.array([10.0, 10.0, 40.0, 10.0, 10.0])
        filtered = filt.apply(signal)

        # O valor indexado 2 (que era 40) deve virar a média dos vizinhos (10+40+10)/3 = 20
        self.assertAlmostEqual(filtered[2], 20.0, places=4)
        self.assertEqual(len(filtered), len(signal))


class TestQuaternionMath(unittest.TestCase):
    """Testes da estrutura matemática do Quaternion."""

    def test_identity_creation(self) -> None:
        """Garante que o quaternion identidade não causa rotação (w=1, x=y=z=0)."""
        q = Quaternion.identity()
        self.assertEqual(q.w, 1.0)
        self.assertEqual(q.x, 0.0)
        self.assertEqual(q.y, 0.0)
        self.assertEqual(q.z, 0.0)

    def test_normalization(self) -> None:
        """Quaternions desgastados por ponto flutuante devem voltar a ter norma 1."""
        q_raw = Quaternion(2.0, 0.0, 0.0, 0.0)
        q_norm = q_raw.normalized()
        self.assertEqual(q_norm.w, 1.0)

    def test_euler_round_trip(self) -> None:
        """Conversão Euler -> Quaternion -> Euler deve manter os mesmos ângulos."""
        # Rotações de teste em radianos (Roll, Pitch, Yaw)
        orig_roll, orig_pitch, orig_yaw = 0.1, -0.2, 0.5
        
        q = Quaternion.from_euler(orig_roll, orig_pitch, orig_yaw)
        calc_roll, calc_pitch, calc_yaw = q.to_euler()

        self.assertAlmostEqual(calc_roll, orig_roll, places=5)
        self.assertAlmostEqual(calc_pitch, orig_pitch, places=5)
        self.assertAlmostEqual(calc_yaw, orig_yaw, places=5)


class TestMadgwickAttitudeEstimator(unittest.TestCase):
    """Testes do Wrapper do Filtro de Madgwick."""

    def test_estimator_updates_and_keeps_normalized(self) -> None:
        """Garante que o estimador processe o passo e retorne um quaternion válido."""
        estimator = MadgwickAttitudeEstimator(gain=0.033)
        
        # Simula o smartphone parado (só gravidade agindo no eixo Z)
        q_atual = estimator.update(
            gx=0.0, gy=0.0, gz=0.0,       # Sem rotação
            ax=0.0, ay=0.0, az=9.81,      # Gravidade pura
            mx=20.0, my=0.0, mz=-30.0,    # Norte magnético simulado
            dt=0.01                       # 10ms de intervalo
        )

        # O retorno deve ser um objeto Quaternion
        self.assertIsInstance(q_atual, Quaternion)
        
        # A norma do array interno do quaternion resultante deve ser obrigatoriamente 1.0
        norma = np.linalg.norm(q_atual.to_array())
        self.assertAlmostEqual(norma, 1.0, places=6)


if __name__ == "__main__":
    unittest.main()