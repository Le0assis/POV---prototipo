"""Testes da Etapa 2 (Magnitude da aceleração)."""

import unittest

import numpy as np

from pdr.magnitude import compute_acceleration_magnitude, compute_magnitude_series


class FakeSample:
    """Objeto mínimo com .ax/.ay/.az, para testar compute_magnitude_series
    sem depender do pacote `sensors` (duck typing)."""

    def __init__(self, ax: float, ay: float, az: float) -> None:
        self.ax, self.ay, self.az = ax, ay, az


class TestMagnitude(unittest.TestCase):

    def test_scalar_input_returns_float(self) -> None:
        result = compute_acceleration_magnitude(3.0, 4.0, 0.0)
        self.assertIsInstance(result, float)
        self.assertAlmostEqual(result, 5.0)

    def test_zero_vector_has_zero_magnitude(self) -> None:
        self.assertAlmostEqual(compute_acceleration_magnitude(0.0, 0.0, 0.0), 0.0)

    def test_array_input_returns_array(self) -> None:
        result = compute_acceleration_magnitude(
            np.array([3.0, 0.0]), 
            np.array([4.0, 0.0]), 
            np.array([0.0, 5.0])
        )
        np.testing.assert_allclose(result, [5.0, 5.0])

    def test_orientation_invariance(self) -> None:
        """A magnitude deve ser a mesma independente de como o vetor
        está distribuído entre os eixos (propriedade central da Etapa 2)."""
        m1 = compute_acceleration_magnitude(1.0, 2.0, 3.0)
        m2 = compute_acceleration_magnitude(3.0, 1.0, 2.0)  # eixos trocados
        self.assertAlmostEqual(m1, m2)

    def test_compute_magnitude_series(self) -> None:
        samples = [FakeSample(3, 4, 0), FakeSample(0, 0, 5)]
        result = compute_magnitude_series(samples)
        np.testing.assert_allclose(result, [5.0, 5.0])


if __name__ == "__main__":
    unittest.main()