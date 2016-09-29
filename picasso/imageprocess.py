"""
    picasso/imageprocess
    ~~~~~~~~~~~~~~~~~~~~

    Image processing functions

    :author: Joerg Schnitzbauer, 2016
    :copyright: Copyright (c) 2016 Jungmann Lab, Max Planck Institute of Biochemistry
"""
import matplotlib.pyplot as _plt
import numpy as _np
from numpy import fft as _fft
import lmfit as _lmfit
from tqdm import tqdm as _tqdm


_plt.style.use('ggplot')


def xcorr(imageA, imageB):
    FimageA = _fft.fft2(imageA)
    CFimageB = _np.conj(_fft.fft2(imageB))
    return _fft.fftshift(_np.real(_fft.ifft2((FimageA * CFimageB)))) / _np.sqrt(imageA.size)


def get_image_shift(imageA, imageB, box, roi=None, display=False):
    """ Computes the shift from imageA to imageB """
    # Compute image correlation
    XCorr = xcorr(imageA, imageB)
    # Cut out center roi
    Y, X = imageA.shape
    if roi is not None:
        Y_ = int((Y - roi) / 2)
        X_ = int((X - roi) / 2)
        XCorr_ = XCorr[Y_:-Y_, X_:-X_]
    else:
        Y_ = X_ = 0
        XCorr_ = XCorr
    # A quarter of the fit ROI
    fit_X = int(box / 2)
    # A coordinate grid for the fitting ROI
    y, x = _np.mgrid[-fit_X:fit_X+1, -fit_X:fit_X+1]
    # Find the brightest pixel and cut out the fit ROI
    y_max_, x_max_ = _np.unravel_index(XCorr_.argmax(), XCorr_.shape)
    FitROI = XCorr[y_max_ - fit_X + Y_:y_max_ + fit_X + Y_ + 1, x_max_ - fit_X + X_:x_max_ + fit_X + X_ + 1]

    # The fit model
    def flat_2d_gaussian(a, xc, yc, s, b):
        A = a * _np.exp(-0.5 * ((x - xc)**2 + (y - yc)**2) / s**2) + b
        return A.flatten()
    gaussian2d = _lmfit.Model(flat_2d_gaussian, name='2D Gaussian', independent_vars=[])

    # Set up initial parameters and fit
    params = _lmfit.Parameters()
    params.add('a', value=FitROI.max(), vary=True, min=0)
    params.add('xc', value=0, vary=True)
    params.add('yc', value=0, vary=True)
    params.add('s', value=1, vary=True, min=0)
    params.add('b', value=FitROI.min(), vary=True, min=0)
    results = gaussian2d.fit(FitROI.flatten(), params)

    # Get maximum coordinates and add offsets
    xc = results.best_values['xc']
    yc = results.best_values['yc']
    xc += X_ + x_max_
    yc += Y_ + y_max_

    if display:
        _plt.figure(figsize=(17, 10))
        _plt.subplot(1, 3, 1)
        _plt.imshow(imageA, interpolation='none')
        _plt.subplot(1, 3, 2)
        _plt.imshow(imageB, interpolation='none')
        _plt.subplot(1, 3, 3)
        _plt.imshow(XCorr, interpolation='none')
        _plt.plot(xc, yc, 'x')
        _plt.show()

    xc -= X / 2
    yc -= Y / 2
    return -yc, -xc


def rcc(segments, max_shift=None, callback=None):
    n_segments = len(segments)
    n_pairs = int(n_segments * (n_segments - 1) / 2)
    rij = _np.zeros((n_pairs, 2))
    A = _np.zeros((n_pairs, n_segments - 1))
    flag = 0
    with _tqdm(total=n_pairs, desc='Correlating image pairs', unit='pairs') as progress_bar:
        if callback is not None:
            callback(0)
        for i in range(n_segments - 1):
            for j in range(i+1, n_segments):
                progress_bar.update()
                dyij, dxij = get_image_shift(segments[i], segments[j], 5, max_shift)
                rij[flag, 0] = dyij
                rij[flag, 1] = dxij
                A[flag, i:j] = 1
                flag += 1
                if callback is not None:
                    callback(flag)
    Dj = _np.dot(_np.linalg.pinv(A), rij)
    shift_y = _np.insert(_np.cumsum(Dj[:, 0]), 0, 0)
    shift_x = _np.insert(_np.cumsum(Dj[:, 1]), 0, 0)
    return shift_y, shift_x
