from ._base import BaseNonlinearFun
from ._convection import ConvectionNonlinearFun
from ._general_nonlinear import GeneralNonlinearFun1d
from ._gradient_norm import GradientNormNonlinearFun
from ._polynomial import PolynomialNonlinearFun
from ._vorticity_convection import (
    VorticityConvection2d,
    VorticityConvection2dKolmogorov,
)
from ._zero import ZeroNonlinearFun

__all__ = [
    "BaseNonlinearFun",
    "ConvectionNonlinearFun",
    "GeneralNonlinearFun1d",
    "GradientNormNonlinearFun",
    "PolynomialNonlinearFun",
    "VorticityConvection2d",
    "VorticityConvection2dKolmogorov",
    "ZeroNonlinearFun",
]
