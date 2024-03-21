from jaxtyping import Array, Complex

from .._base_stepper import BaseStepper
from .._spectral import build_laplace_operator
from ..nonlin_fun import PolynomialNonlinearFun


class AllenCahn(BaseStepper):
    diffusivity: float
    first_order_coefficient: float
    third_order_coefficient: float
    dealiasing_fraction: float

    def __init__(
        self,
        num_spatial_dims: int,
        domain_extent: float,
        num_points: int,
        dt: float,
        *,
        diffusivity: float = 5e-3,
        first_order_coefficient: float = 1.0,
        third_order_coefficient: float = -1.0,
        order: int = 2,
        # Needs lower value due to cubic nonlinearity
        dealiasing_fraction: float = 1 / 2,
        num_circle_points: int = 16,
        circle_radius: float = 1.0,
    ):
        self.diffusivity = diffusivity
        self.first_order_coefficient = first_order_coefficient
        self.third_order_coefficient = third_order_coefficient
        self.dealiasing_fraction = dealiasing_fraction
        super().__init__(
            num_spatial_dims=num_spatial_dims,
            domain_extent=domain_extent,
            num_points=num_points,
            dt=dt,
            num_channels=1,
            order=order,
            num_circle_points=num_circle_points,
            circle_radius=circle_radius,
        )

    def _build_linear_operator(
        self,
        derivative_operator: Complex[Array, "D ... (N//2)+1"],
    ) -> Complex[Array, "1 ... (N//2)+1"]:
        laplace = build_laplace_operator(derivative_operator, order=2)
        linear_operator = self.diffusivity * laplace + self.first_order_coefficient
        return linear_operator

    def _build_nonlinear_fun(
        self,
        derivative_operator: Complex[Array, "D ... (N//2)+1"],
    ) -> PolynomialNonlinearFun:
        return PolynomialNonlinearFun(
            self.num_spatial_dims,
            self.num_points,
            dealiasing_fraction=self.dealiasing_fraction,
            coefficients=[0.0, 0.0, 0.0, self.third_order_coefficient],
        )
