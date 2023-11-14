import numpy as np
from scipy.stats import norm

from pygama.math.functions.gauss_on_linear import gauss_on_linear
from pygama.math.functions.sum_dists import sum_dists


def line(x, m, b):
    return m * x + b


def quad(x, x_lower, m, b):
    return m * (x**2 - x_lower**2) / 2 + b * (x - x_lower)


def test_gauss_on_linear_pdf():

    x = np.arange(-10, 10)
    mu = 1
    sigma = 2
    x_lower = np.amin(x)
    x_upper = np.amax(x)
    m = 2
    b = 3
    n_sig = 10
    n_bkg = 20

    pars = np.array([n_sig, mu, sigma, n_bkg, m, b, x_lower, x_upper], dtype=float)

    assert isinstance(gauss_on_linear, sum_dists)

    y_direct = gauss_on_linear.get_pdf(x, *pars)

    normalization = m / 2 * (x_upper**2 - x_lower**2) + b * (x_upper - x_lower)
    scipy_linear = n_bkg * line(x, m, b) / normalization

    scipy_gauss = n_sig * norm.pdf(x, mu, sigma)

    scipy_y = scipy_gauss + scipy_linear

    assert np.allclose(y_direct, scipy_y, rtol=1e-8)

    x_lo = -10
    x_hi = 9

    gauss_on_linear.set_x_lo(x_lo)
    gauss_on_linear.set_x_hi(x_hi)
    y_sig, y_ext = gauss_on_linear.pdf_ext(x, *pars)
    assert np.allclose(y_ext, scipy_y, rtol=1e-8)
    assert np.allclose(y_sig, n_sig + n_bkg, rtol=1e-3)


def test_gauss_on_linear_cdf():

    x = np.arange(-10, 10)
    mu = 1
    sigma = 2
    x_lower = np.amin(x)
    x_upper = np.amax(x)
    m = 2
    b = 3
    n_sig = 10
    n_bkg = 20

    pars = np.array([n_sig, mu, sigma, n_bkg, m, b, x_lower, x_upper], dtype=float)

    assert isinstance(gauss_on_linear, sum_dists)

    y_direct = gauss_on_linear.get_cdf(x, *pars)

    scipy_gauss = n_sig * norm.cdf(x, mu, sigma)
    normalization = m / 2 * (x_upper**2 - x_lower**2) + b * (x_upper - x_lower)
    scipy_linear = n_bkg * quad(x, x_lower, m, b) / normalization

    scipy_y = scipy_gauss + scipy_linear

    assert np.allclose(y_direct, scipy_y, rtol=1e-8)

    gauss_on_linear.set_x_lo(x_lower)
    gauss_on_linear.set_x_hi(x_upper)
    y_ext = gauss_on_linear.cdf_ext(x, *pars)
    assert np.allclose(y_ext, scipy_y, rtol=1e-8)
