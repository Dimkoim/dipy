from __future__ import division

import numpy as np
from numpy import dot
from dipy.core.geometry import sphere2cart
from dipy.core.geometry import vec2vec_rotmat


# Diffusion coefficients for white matter tracts, in mm^2/s
#
# Based roughly on values from:
#
#   Pierpaoli, Basser, "Towards a Quantitative Assessment of Diffusion
#   Anisotropy", Magnetic Resonance in Medicine, 1996; 36(6):893-906.
#
diffusion_evals = np.array([1500e-6, 400e-6, 400e-6])


def _check_directions(angles):
    """
    Helper function to check if direction ground truth have the right format
    and are in cartesian coordinates

    Parameters
    -----------
    angles : array (K,2) or (K, 3)
        List of K polar angles (in degrees) for the sticks or array of K
        sticks as unit vectors.

    Returns
    --------
    sticks : (M,3)
        Sticks in cartesian coordinates.
    """
    angles = np.array(angles)
    if angles.shape[-1] == 3:
        sticks = angles
    else:
        sticks = [sphere2cart(1, np.deg2rad(pair[0]), np.deg2rad(pair[1]))
                  for pair in angles]
        sticks = np.array(sticks)

    return sticks


def _add_gaussian(sig, noise1, noise2):
    """
    Helper function to add_noise

    This one simply adds one of the Gaussians to the sig and ignores the other
    one.
    """
    return sig + noise1


def _add_rician(sig, noise1, noise2):
    """
    Helper function to add_noise.

    This does the same as abs(sig + complex(noise1, noise2))

    """
    return np.sqrt((sig + noise1) ** 2 + noise2 ** 2)


def _add_rayleigh(sig, noise1, noise2):
    """
    Helper function to add_noise

    The Rayleigh distribution is $\sqrt\{Gauss_1^2 + Gauss_2^2}$.

    """
    return sig + np.sqrt(noise1 ** 2 + noise2 ** 2)


def add_noise(signal, snr, S0, noise_type='rician'):
    r""" Add noise of specified distribution to the signal from a single voxel.

    Parameters
    -----------
    signal : 1-d ndarray
        The signal in the voxel.
    snr : float
        The desired signal-to-noise ratio. (See notes below.)
        If `snr` is None, return the signal as-is.
    S0 : float
        Reference signal for specifying `snr`.
    noise_type : string, optional
        The distribution of noise added. Can be either 'gaussian' for Gaussian
        distributed noise, 'rician' for Rice-distributed noise (default) or
        'rayleigh' for a Rayleigh distribution.

    Returns
    --------
    signal : array, same shape as the input
        Signal with added noise.

    Notes
    -----
    SNR is defined here, following [1]_, as ``S0 / sigma``, where ``sigma`` is
    the standard deviation of the two Gaussian distributions forming the real
    and imaginary components of the Rician noise distribution (see [2]_).

    References
    ----------
    .. [1] Descoteaux, Angelino, Fitzgibbons and Deriche (2007) Regularized,
           fast and robust q-ball imaging. MRM, 58: 497-510
    .. [2] Gudbjartson and Patz (2008). The Rician distribution of noisy MRI
           data. MRM 34: 910-914.

    Examples
    --------
    >>> signal = np.arange(800).reshape(2, 2, 2, 100)
    >>> signal_w_noise = add_noise(signal, 10., 100., noise_type='rician')

    """
    if snr is None:
        return signal

    sigma = S0 / snr

    noise_adder = {'gaussian': _add_gaussian,
                   'rician': _add_rician,
                   'rayleigh': _add_rayleigh}

    noise1 = np.random.normal(0, sigma, size=signal.shape)

    if noise_type == 'gaussian':
        noise2 = None
    else:
        noise2 = np.random.normal(0, sigma, size=signal.shape)

    return noise_adder[noise_type](signal, noise1, noise2)


def sticks_and_ball(gtab, d=0.0015, S0=100, angles=[(0, 0), (90, 0)],
                    fractions=[35, 35], snr=20):
    """ Simulate the signal for a Sticks & Ball model.

    Parameters
    -----------
    gtab : GradientTable
        Signal measurement directions.
    d : float
        Diffusivity value.
    S0 : float
        Unweighted signal value.
    angles : array (K,2) or (K, 3)
        List of K polar angles (in degrees) for the sticks or array of K
        sticks as unit vectors.
    fractions : float
        Percentage of each stick.  Remainder to 100 specifies isotropic
        component.
    snr : float
        Signal to noise ratio, assuming Rician noise.  If set to None, no
        noise is added.

    Returns
    --------
    S : (N,) ndarray
        Simulated signal.
    sticks : (M,3)
        Sticks in cartesian coordinates.

    References
    ----------
    .. [1] Behrens et al., "Probabilistic diffusion
           tractography with multiple fiber orientations:  what can we gain?",
           Neuroimage, 2007.

    """
    fractions = [f / 100. for f in fractions]
    f0 = 1 - np.sum(fractions)
    S = np.zeros(len(gtab.bvals))

    sticks = _check_directions(angles)

    for (i, g) in enumerate(gtab.bvecs[1:]):
        S[i + 1] = f0*np.exp(-gtab.bvals[i + 1]*d) + \
            np.sum([fractions[j]*np.exp(-gtab.bvals[i + 1]*d*np.dot(s, g)**2)
                   for (j, s) in enumerate(sticks)])

        S[i + 1] = S0 * S[i + 1]

    S[gtab.b0s_mask] = S0
    S = add_noise(S, snr, S0)

    return S, sticks


def single_tensor(gtab, S0=1, evals=None, evecs=None, snr=None):
    """ Simulated Q-space signal with a single tensor.

    Parameters
    -----------
    gtab : GradientTable
        Measurement directions.
    S0 : double,
        Strength of signal in the presence of no diffusion gradient (also
        called the ``b=0`` value).
    evals : (3,) ndarray
        Eigenvalues of the diffusion tensor.  By default, values typical for
        prolate white matter are used.
    evecs : (3, 3) ndarray
        Eigenvectors of the tensor.  You can also think of this as a rotation
        matrix that transforms the direction of the tensor. The eigenvectors
        needs to be column wise.
    snr : float
        Signal to noise ratio, assuming Rician noise.  None implies no noise.

    Returns
    --------
    S : (N,) ndarray
        Simulated signal: ``S(q, tau) = S_0 e^(-b g^T R D R.T g)``.

    References
    ----------
    .. [1] M. Descoteaux, "High Angular Resolution Diffusion MRI: from Local
           Estimation to Segmentation and Tractography", PhD thesis,
           University of Nice-Sophia Antipolis, p. 42, 2008.
    .. [2] E. Stejskal and J. Tanner, "Spin diffusion measurements: spin echos
           in the presence of a time-dependent field gradient", Journal of
           Chemical Physics, nr. 42, pp. 288--292, 1965.

    """
    if evals is None:
        evals = diffusion_evals

    if evecs is None:
        evecs = np.eye(3)

    out_shape = gtab.bvecs.shape[:gtab.bvecs.ndim - 1]
    gradients = gtab.bvecs.reshape(-1, 3)

    R = np.asarray(evecs)
    S = np.zeros(len(gradients))
    D = dot(dot(R, np.diag(evals)), R.T)

    for (i, g) in enumerate(gradients):
        S[i] = S0 * np.exp(-gtab.bvals[i] * dot(dot(g.T, D), g))

    S = add_noise(S, snr, S0)

    return S.reshape(out_shape)


def multi_tensor(gtab, mevals, S0=100, angles=[(0, 0), (90, 0)],
                 fractions=[50, 50], snr=20):
    r""" Simulate a Multi-Tensor signal.

    Parameters
    -----------
    gtab : GradientTable
    mevals : array (K, 3)
        each tensor's eigenvalues in each row
    S0 : float
        Unweighted signal value (b0 signal).
    angles : array (K,2) or (K,3)
        List of K tensor directions in polar angles (in degrees) or unit
        vectors
    fractions : float
        Percentage of the contribution of each tensor. The sum of fractions
        should be equal to 100%.
    snr : float
        Signal to noise ratio, assuming Rician noise.  If set to None, no
        noise is added.

    Returns
    --------
    S : (N,) ndarray
        Simulated signal.
    sticks : (M,3)
        Sticks in cartesian coordinates.

    Examples
    --------
    >>> import numpy as np
    >>> from dipy.sims.voxel import multi_tensor
    >>> from dipy.data import get_data
    >>> from dipy.core.gradients import gradient_table
    >>> from dipy.io.gradients import read_bvals_bvecs
    >>> fimg, fbvals, fbvecs = get_data('small_101D')
    >>> bvals, bvecs = read_bvals_bvecs(fbvals, fbvecs)
    >>> gtab = gradient_table(bvals, bvecs)
    >>> mevals=np.array(([0.0015, 0.0003, 0.0003],[0.0015, 0.0003, 0.0003]))
    >>> e0 = np.array([1, 0, 0.])
    >>> e1 = np.array([0., 1, 0])
    >>> S = multi_tensor(gtab, mevals)

    """
    if np.round(np.sum(fractions), 2) != 100.0:
        raise ValueError('Fractions should sum to 100')

    fractions = [f / 100. for f in fractions]

    S = np.zeros(len(gtab.bvals))

    sticks = _check_directions(angles)

    for i in range(len(fractions)):
            S = S + fractions[i] * single_tensor(gtab, S0=S0, evals=mevals[i],
                                                 evecs=all_tensor_evecs(
                                                     sticks[i]).T,
                                                 snr=None)

    return add_noise(S, snr, S0), sticks


def multi_tensor_dki(gtab, mevals, S0=100, angles=[(90., 0.), (90., 0.)],
                     fractions=[50, 50], snr=20):

    r""" Simulate the diffusion-weight signal based on the DKI model

    Parameters
    -----------
    gtab : GradientTable
    mevals : array (K, 3)
        eigenvalues of the diffusion tensor for each individual compartment
    S0 : float
        Unweighted signal value (b0 signal).
    angles : array (K,2) or (K,3)
        List of K tensor directions of the diffusion tensor of each compartment
        in polar angles (in degrees) or unit vectors
    fractions : float (K,)
        Percentage of the contribution of each tensor. The sum of fractions
        should be equal to 100%.
    snr : float
        Signal to noise ratio, assuming Rician noise.  If set to None, no
        noise is added.

    Returns
    --------
    S : (N,) ndarray
        Simulated signal based on the DKI model.
    dt : (6,)
        elements of the diffusion tensor.
    kt : (15,)
        elements of the kurtosis tensor.

    Notes
    -----
    Simulations are based on multicompartmental models which assumes that
    tissue is well described by impermeable diffusion compartments
    characterized by their only diffusion tensor. Since simulations are based
    on the DKI model, coefficients larger than the fourth order of the signal's
    taylor expansion approximation are neglected.

    Examples
    --------
    >>> import numpy as np
    >>> from dipy.sims.voxel import multi_tensor_dki
    >>> from dipy.data import get_data
    >>> from dipy.core.gradients import gradient_table
    >>> from dipy.io.gradients import read_bvals_bvecs
    >>> fimg, fbvals, fbvecs = get_data('small_64D')
    >>> bvals, bvecs = read_bvals_bvecs(fbvals, fbvecs)
    >>> bvals_2s = np.concatenate((bvals, bvals * 2), axis=0)
    >>> bvecs_2s = np.concatenate((bvecs, bvecs), axis=0)
    >>> gtab = gradient_table(bvals_2s, bvecs_2s)
    >>> mevals = np.array([[0.00099, 0, 0],[0.00226, 0.00087, 0.00087]])
    >>> S, dt, kt =  multi_tensor_dki(gtab, mevals)

    References
    ----------
    .. [1] R. Neto Henriques et al., "Exploring the 3D geometry of the
           diffusion kurtosis tensor - Impact on the development of robust
           tractography procedures and novel biomarkers", NeuroImage (2015)
           111, 85-99.
    """

    if np.round(np.sum(fractions), 2) != 100.0:
        raise ValueError('Fractions should sum to 100')

    fractions = [f / 100. for f in fractions]

    S = np.zeros(len(gtab.bvals))

    sticks = _check_directions(angles)

    # computing a 3D matrix containing the individual DT components
    D_comps = np.zeros((len(fractions), 3, 3))
    for i in range(len(fractions)):
        R = all_tensor_evecs(sticks[i])
        D_comps[i] = dot(dot(R, np.diag(mevals[i])), R.T)

    # compute voxel's DT
    DT = np.zeros((3, 3))
    for i in range(len(fractions)):
        DT = DT + fractions[i]*D_comps[i]
    dt = np.array([D[0][0], D[1][1], D[2][2], D[0][1], D[0][2], D[1][2]])

    # compute voxel's MD
    MD = (D[0][0] + D[1][1] + D[2][2]) / 3

    # compute voxel's KT
    kt = np.zeros((15))
    kt[0] = kurtosis_element(D_comps, fractions, 0, 0, 0, 0, DT, MD)
    kt[1] = kurtosis_element(D_comps, fractions, 1, 1, 1, 1, DT, MD)
    kt[2] = kurtosis_element(D_comps, fractions, 2, 2, 2, 2, DT, MD)
    kt[3] = kurtosis_element(D_comps, fractions, 0, 0, 0, 1, DT, MD)
    kt[4] = kurtosis_element(D_comps, fractions, 0, 0, 0, 2, DT, MD)
    kt[5] = kurtosis_element(D_comps, fractions, 0, 1, 1, 1, DT, MD)
    kt[6] = kurtosis_element(D_comps, fractions, 1, 1, 1, 2, DT, MD)
    kt[7] = kurtosis_element(D_comps, fractions, 0, 2, 2, 2, DT, MD)
    kt[8] = kurtosis_element(D_comps, fractions, 1, 2, 2, 2, DT, MD)
    kt[9] = kurtosis_element(D_comps, fractions, 0, 0, 1, 1, DT, MD)
    kt[10] = kurtosis_element(D_comps, fractions, 0, 0, 2, 2, DT, MD)
    kt[11] = kurtosis_element(D_comps, fractions, 1, 1, 2, 2, DT, MD)
    kt[12] = kurtosis_element(D_comps, fractions, 0, 0, 1, 2, DT, MD)
    kt[13] = kurtosis_element(D_comps, fractions, 0, 1, 1, 2, DT, MD)
    kt[14] = kurtosis_element(D_comps, fractions, 0, 1, 2, 2, DT, MD)

    # compute S based on the DT and KT
    S = DKI_signal(gtab, dt, kt, S0, snr)

    return S, dt, kt


def kurtosis_element(D_comps, frac, ind_i, ind_j, ind_k, ind_l, DT=None,
                     MD=None):
    r""" Computes the diffusion kurtosis tensor element (with indexes i, j, k
    and l) based on the individual diffusion tensor components of a
    multicompartmental model.

    Parameters
    -----------
    D_comps : (K,3,3) ndarray
        Diffusion tensors for all K individual compartment of the
        multicompartmental model.
    frac : float
        Percentage of the contribution of each tensor. The sum of fractions
        should be equal to 100%.
    ind_i : int
        Element's index i (0 for x, 1 for y, 2 for z)
    ind_j : int
        Element's index j (0 for x, 1 for y, 2 for z)
    ind_k : int
        Element's index k (0 for x, 1 for y, 2 for z)
    ind_l: int
        Elements index l (0 for x, 1 for y, 2 for z)
    DT : (3,3) ndarray (optional)
        Voxel's global diffusion tensor.
    MD : float (optional)
        Voxel's global mean diffusivity.

    Returns
    --------
    wijkl : float
            kurtosis tensor element of index i, j, k, l

    Notes
    --------
    wijkl is calculated using equation 8 given in [1]_

    References
    ----------
    .. [1] R. Neto Henriques et al., "Exploring the 3D geometry of the
           diffusion kurtosis tensor - Impact on the development of robust
           tractography procedures and novel biomarkers", NeuroImage (2015)
           111, 85-99.
    """

    if DT is None:
        DT = np.zeros((3, 3))
        for i in range(len(frac)):
            DT = DT + frac[i]*D_comps[i]

    if MD is None:
        MD = (DT[0][0] + DT[1][1] + DT[2][2]) / 3

    wijkl = 0

    for f in range(len(frac)):
        wijkl = wijkl + frac[f] * (
                D_comps[f][ind_i][ind_j]*D_comps[f][ind_k][ind_l] +
                D_comps[f][ind_i][ind_k]*D_comps[f][ind_j][ind_l] +
                D_comps[f][ind_i][ind_l]*D_comps[f][ind_j][ind_k])

    wijkl = (wijkl - DT[ind_i][ind_j]*DT[ind_k][ind_l] -
             DT[ind_i][ind_k]*DT[ind_j][ind_l] -
             DT[ind_i][ind_l]*DT[ind_j][ind_k]) / (MD**2)

    return wijkl


def DKI_signal(gtab, dt, kt, S0=150, snr=None):
    r""" Simulated signal based on the diffusion and diffusion kurtosis
    tensors. Simulations are preformed assuming the DKI model.

    Parameters
    -----------
    gtab : GradientTable
        Measurement directions.
    dt : (6,) ndarray
        Elements of the diffusion tensor.
    kt : (15, ) ndarray
        Elements of the diffusion kurtosis tensor.
    S0 : float (optional)
        Strength of signal in the presence of no diffusion gradient.
    snr : float (optional)
        Signal to noise ratio, assuming Rician noise.  None implies no noise.

    Returns
    --------
    S : (N,) ndarray
        Simulated signal based on the DKI model:

    .. math::

        S=S_{0}e^{-bD+\frac{1}{6}b^{2}D^{2}K}

    References
    ----------
    .. [1] R. Neto Henriques et al., "Exploring the 3D geometry of the
           diffusion kurtosis tensor - Impact on the development of robust
           tractography procedures and novel biomarkers", NeuroImage (2015)
           111, 85-99.
    """
    dt = np.array(dt)
    kt = np.array(kt)

    A = dki_design_matrix(gtab)

    # define vector of DKI parameters
    MD = sum(dt[0:3]) / 3
    X = np.concatenate((dt, kt*MD*MD, np.array([np.log(S0)])), axis=0)

    # Compute signals based on the DKI model
    S = np.exp(dot(A, X))

    S = add_noise(S, snr, S0)

    return S


def dki_design_matrix(gtab):
    r""" Constructs B design matrix for DKI

    Parameters
    ---------
    gtab : GradientTable
        Measurement directions.

    Returns
    -------
    design_matrix : array (N,22)
          Design matrix or B matrix for the DKI model
            design_matrix[j, :] = (Bxx, Byy, Bzz, Bxy, Bxz, Byz,
                                   Bxxxx, Byyyy, Bzzzz, Bxxxy, Bxxxz,
                                   Bxyyy, Byyyz, Bxzzz, Byzzz, Bxxyy,
                                   Bxxzz, Byyzz, Bxxyz, Bxyyz, Bxyzz,
                                   BlogS0)
    """
    b = gtab.bvals
    bvec = gtab.bvecs

    B = np.zeros((len(b), 22))
    B[:, 0] = -b * bvec[:, 0] * bvec[:, 0]
    B[:, 1] = -b * bvec[:, 1] * bvec[:, 1]
    B[:, 2] = -b * bvec[:, 2] * bvec[:, 2]
    B[:, 3] = -2 * b * bvec[:, 0] * bvec[:, 1]
    B[:, 4] = -2 * b * bvec[:, 0] * bvec[:, 2]
    B[:, 5] = -2 * b * bvec[:, 1] * bvec[:, 2]
    B[:, 6] = b * b * bvec[:, 0]**4 / 6
    B[:, 7] = b * b * bvec[:, 1]**4 / 6
    B[:, 8] = b * b * bvec[:, 2]**4 / 6
    B[:, 9] = 4 * b * b * bvec[:, 0]**3 * bvec[:, 1] / 6
    B[:, 10] = 4 * b * b * bvec[:, 0]**3 * bvec[:, 2] / 6
    B[:, 11] = 4 * b * b * bvec[:, 1]**3 * bvec[:, 0] / 6
    B[:, 12] = 4 * b * b * bvec[:, 1]**3 * bvec[:, 2] / 6
    B[:, 13] = 4 * b * b * bvec[:, 2]**3 * bvec[:, 0] / 6
    B[:, 14] = 4 * b * b * bvec[:, 2]**3 * bvec[:, 1] / 6
    B[:, 15] = b * b * bvec[:, 0]**2 * bvec[:, 1]**2
    B[:, 16] = b * b * bvec[:, 0]**2 * bvec[:, 2]**2
    B[:, 17] = b * b * bvec[:, 1]**2 * bvec[:, 2]**2
    B[:, 18] = 2 * b * b * bvec[:, 0]**2 * bvec[:, 1] * bvec[:, 2]
    B[:, 19] = 2 * b * b * bvec[:, 1]**2 * bvec[:, 0] * bvec[:, 2]
    B[:, 20] = 2 * b * b * bvec[:, 2]**2 * bvec[:, 0] * bvec[:, 1]
    B[:, 21] = np.ones(len(b))

    return B


def single_tensor_odf(r, evals=None, evecs=None):
    """ Simulated ODF with a single tensor.

    Parameters
    ----------
    r : (N,3) or (M,N,3) ndarray
        Measurement positions in (x, y, z), either as a list or on a grid.
    evals : (3,)
        Eigenvalues of diffusion tensor.  By default, use values typical for
        prolate white matter.
    evecs : (3, 3) ndarray
        Eigenvectors of the tensor.  You can also think of these as the
        rotation matrix that determines the orientation of the diffusion
        tensor.

    Returns
    -------
    ODF : (N,) ndarray
        The diffusion probability at ``r`` after time ``tau``.

    References
    ----------
    .. [1] Aganj et al., "Reconstruction of the Orientation Distribution
           Function in Single- and Multiple-Shell q-Ball Imaging Within
           Constant Solid Angle", Magnetic Resonance in Medicine, nr. 64,
           pp. 554--566, 2010.

    """
    if evals is None:
        evals = diffusion_evals

    if evecs is None:
        evecs = np.eye(3)

    out_shape = r.shape[:r.ndim - 1]

    R = np.asarray(evecs)
    D = dot(dot(R, np.diag(evals)), R.T)
    Di = np.linalg.inv(D)
    r = r.reshape(-1, 3)
    P = np.zeros(len(r))
    for (i, u) in enumerate(r):
        P[i] = (dot(dot(u.T, Di), u)) ** (3 / 2)

    return (1 / (4 * np.pi * np.prod(evals) ** (1 / 2) * P)).reshape(out_shape)


def all_tensor_evecs(e0):
    """Given the principle tensor axis, return the array of all
    eigenvectors (or, the rotation matrix that orientates the tensor).

    Parameters
    ----------
    e0 : (3,) ndarray
        Principle tensor axis.

    Returns
    -------
    evecs : (3,3) ndarray
        Tensor eigenvectors.

    """
    axes = np.eye(3)
    mat = vec2vec_rotmat(axes[0], e0)
    e1 = np.dot(mat, axes[1])
    e2 = np.dot(mat, axes[2])
    return np.array([e0, e1, e2])


def multi_tensor_odf(odf_verts, mevals, angles, fractions):
    r'''Simulate a Multi-Tensor ODF.

    Parameters
    ----------
    odf_verts : (N,3) ndarray
        Vertices of the reconstruction sphere.
    mevals : sequence of 1D arrays,
        Eigen-values for each tensor.
    angles : sequence of 2d tuples,
        Sequence of principal directions for each tensor in polar angles
        or cartesian unit coordinates.
    fractions : sequence of floats,
        Percentages of the fractions for each tensor.

    Returns
    -------
    ODF : (N,) ndarray
        Orientation distribution function.

    Examples
    --------
    Simulate a MultiTensor ODF with two peaks and calculate its exact ODF.

    >>> import numpy as np
    >>> from dipy.sims.voxel import multi_tensor_odf, all_tensor_evecs
    >>> from dipy.data import get_sphere
    >>> sphere = get_sphere('symmetric724')
    >>> vertices, faces = sphere.vertices, sphere.faces
    >>> mevals = np.array(([0.0015, 0.0003, 0.0003],[0.0015, 0.0003, 0.0003]))
    >>> angles = [(0, 0), (90, 0)]
    >>> odf = multi_tensor_odf(vertices, mevals, angles, [50, 50])

    '''

    mf = [f / 100. for f in fractions]

    sticks = _check_directions(angles)

    odf = np.zeros(len(odf_verts))

    mevecs = []
    for s in sticks:
        mevecs += [all_tensor_evecs(s).T]

    for (j, f) in enumerate(mf):
        odf += f * single_tensor_odf(odf_verts,
                                     evals=mevals[j], evecs=mevecs[j])
    return odf


def single_tensor_rtop(evals=None, tau=1.0 / (4 * np.pi ** 2)):
    r'''Simulate a Multi-Tensor rtop.

    Parameters
    ----------
    evals : 1D arrays,
        Eigen-values for the tensor.  By default, values typical for prolate
        white matter are used.
    tau : float,
        diffusion time. By default the value that makes q=sqrt(b).

    Returns
    -------
    rtop : float,
        Return to origin probability.

    References
    ----------
    .. [1] Cheng J., "Estimation and Processing of Ensemble Average Propagator
           and Its Features in Diffusion MRI", PhD Thesis, 2012.

    '''
    if evals is None:
        evals = diffusion_evals

    rtop = 1.0 / np.sqrt((4 * np.pi * tau) ** 3 * np.prod(evals))
    return rtop


def multi_tensor_rtop(mf, mevals=None, tau=1 / (4 * np.pi ** 2)):
    r'''Simulate a Multi-Tensor rtop.

    Parameters
    ----------
    mf : sequence of floats, bounded [0,1]
        Percentages of the fractions for each tensor.
    mevals : sequence of 1D arrays,
        Eigen-values for each tensor.  By default, values typical for prolate
        white matter are used.
    tau : float,
        diffusion time. By default the value that makes q=sqrt(b).

    Returns
    -------
    rtop : float,
        Return to origin probability.

    References
    ----------
    .. [1] Cheng J., "Estimation and Processing of Ensemble Average Propagator
           and Its Features in Diffusion MRI", PhD Thesis, 2012.

    '''
    rtop = 0

    if mevals is None:
        mevals = [None, ] * len(mf)

    for j, f in enumerate(mf):
        rtop += f * single_tensor_rtop(mevals[j], tau=tau)
    return rtop


def single_tensor_pdf(r, evals=None, evecs=None, tau=1 / (4 * np.pi ** 2)):
    """Simulated ODF with a single tensor.

    Parameters
    ----------
    r : (N,3) or (M,N,3) ndarray
        Measurement positions in (x, y, z), either as a list or on a grid.
    evals : (3,)
        Eigenvalues of diffusion tensor.  By default, use values typical for
        prolate white matter.
    evecs : (3, 3) ndarray
        Eigenvectors of the tensor.  You can also think of these as the
        rotation matrix that determines the orientation of the diffusion
        tensor.
    tau : float,
        diffusion time. By default the value that makes q=sqrt(b).


    Returns
    -------
    pdf : (N,) ndarray
        The diffusion probability at ``r`` after time ``tau``.

    References
    ----------
    .. [1] Cheng J., "Estimation and Processing of Ensemble Average Propagator
           and Its Features in Diffusion MRI", PhD Thesis, 2012.

    """
    if evals is None:
        evals = diffusion_evals

    if evecs is None:
        evecs = np.eye(3)

    out_shape = r.shape[:r.ndim - 1]

    R = np.asarray(evecs)
    D = dot(dot(R, np.diag(evals)), R.T)
    Di = np.linalg.inv(D)
    r = r.reshape(-1, 3)
    P = np.zeros(len(r))
    for (i, u) in enumerate(r):
        P[i] = (-dot(dot(u.T, Di), u)) / (4 * tau)

    pdf = (1 / np.sqrt((4 * np.pi * tau) ** 3 * np.prod(evals))) * np.exp(P)

    return pdf.reshape(out_shape)


def multi_tensor_pdf(pdf_points, mevals, angles, fractions,
                     tau=1 / (4 * np.pi ** 2)):
    r'''Simulate a Multi-Tensor ODF.

    Parameters
    ----------
    pdf_points : (N, 3) ndarray
        Points to evaluate the PDF.
    mevals : sequence of 1D arrays,
        Eigen-values for each tensor.  By default, values typical for prolate
        white matter are used.
    angles : sequence,
        Sequence of principal directions for each tensor in polar angles
        or cartesian unit coordinates.
    fractions : sequence of floats,
        Percentages of the fractions for each tensor.
    tau : float,
        diffusion time. By default the value that makes q=sqrt(b).

    Returns
    -------
    pdf : (N,) ndarray,
        Probability density function of the water displacement.

    References
    ----------
    .. [1] Cheng J., "Estimation and Processing of Ensemble Average Propagator
           and its Features in Diffusion MRI", PhD Thesis, 2012.

    '''
    mf = [f / 100. for f in fractions]

    sticks = _check_directions(angles)

    pdf = np.zeros(len(pdf_points))

    mevecs = []
    for s in sticks:
        mevecs += [all_tensor_evecs(s).T]

    for j, f in enumerate(mf):
        pdf += f * single_tensor_pdf(pdf_points,
                                     evals=mevals[j], evecs=mevecs[j], tau=tau)
    return pdf


def single_tensor_msd(evals=None, tau=1 / (4 * np.pi ** 2)):
    r'''Simulate a Multi-Tensor rtop.

    Parameters
    ----------
    evals : 1D arrays,
        Eigen-values for the tensor.  By default, values typical for prolate
        white matter are used.
    tau : float,
        diffusion time. By default the value that makes q=sqrt(b).

    Returns
    -------
    msd : float,
        Mean square displacement.

    References
    ----------
    .. [1] Cheng J., "Estimation and Processing of Ensemble Average Propagator
           and Its Features in Diffusion MRI", PhD Thesis, 2012.

    '''
    if evals is None:
        evals = diffusion_evals

    msd = 2 * tau * np.sum(evals)
    return msd


def multi_tensor_msd(mf, mevals=None, tau=1 / (4 * np.pi ** 2)):
    r'''Simulate a Multi-Tensor rtop.

    Parameters
    ----------
    mf : sequence of floats, bounded [0,1]
        Percentages of the fractions for each tensor.
    mevals : sequence of 1D arrays,
        Eigen-values for each tensor.  By default, values typical for prolate
        white matter are used.
    tau : float,
        diffusion time. By default the value that makes q=sqrt(b).

    Returns
    -------
    msd : float,
        Mean square displacement.

    References
    ----------
    .. [1] Cheng J., "Estimation and Processing of Ensemble Average Propagator
           and Its Features in Diffusion MRI", PhD Thesis, 2012.

    '''
    msd = 0

    if mevals is None:
        mevals = [None, ] * len(mf)

    for j, f in enumerate(mf):
        msd += f * single_tensor_msd(mevals[j], tau=tau)
    return msd

# Use standard naming convention, but keep old names
# for backward compatibility
SticksAndBall = sticks_and_ball
SingleTensor = single_tensor
MultiTensor = multi_tensor
