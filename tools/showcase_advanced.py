"""Reproducible data for the composite Origin showcase figures."""

import csv
from math import cos, exp, log, pi, sqrt
from random import Random


FEATURES = (
    ("Canopy cover", "Surface", -1.72),
    ("Slope angle", "Terrain", 1.48),
    ("Road distance", "Infrastructure", -1.20),
    ("Rainfall intensity", "Water", 1.08),
    ("Relief", "Terrain", 0.84),
    ("Soil depth", "Surface", -0.73),
    ("Stream distance", "Water", -0.64),
    ("Track density", "Infrastructure", 0.55),
    ("Profile curvature", "Terrain", 0.45),
    ("Wetness index", "Water", 0.39),
    ("Bare ground", "Surface", 0.31),
    ("Aspect index", "Terrain", -0.24),
)
FEATURE_GROUPS = {
    "Surface": "#537987", "Terrain": "#A24B74", "Infrastructure": "#C18441", "Water": "#517A54",
}
VALUE_COLORS = ("#15688A", "#3784A6", "#65A6BB", "#A4C0C6", "#C7A5AC", "#CB7586", "#AC3A5D", "#811840")
XPS_PEAKS = (
    ("C–C / C–H", 284.80, 4070, 1.18, 0.20, "#238F86", "#ABD8D2"),
    ("C–O", 286.18, 1830, 1.39, 0.27, "#7661AE", "#D2C5EA"),
    ("C=O", 287.55, 730, 1.18, 0.24, "#C17C38", "#F1D8B6"),
    ("O–C=O", 288.91, 1010, 1.33, 0.25, "#AC506F", "#EAC4CF"),
)
ADVANCED = ("shap-summary", "xps-components")


def interpolate_color(stops, fraction):
    position = fraction * (len(stops) - 1)
    segment = min(int(position), len(stops) - 2)
    weight = position - segment
    return tuple(round(a * (1 - weight) + b * weight) for a, b in zip(stops[segment], stops[segment + 1]))


VALUE_RGB = tuple(tuple(bytes.fromhex(color[1:])) for color in VALUE_COLORS)


def _shap_samples():
    rng = Random("shap-summary")
    for sample in range(1, 141):
        scaled = [rng.betavariate(2.4, 2.4) for _ in FEATURES]
        centered = [2 * val - 1 for val in scaled]
        effects = [w * val * (1 + 0.85 * abs(val)) for (_, _, w), val in zip(FEATURES, centered)]
        # For independent symmetric inputs, each centered main effect has mean zero.
        # Each bilinear interaction has zero conditional mean for an absent feature,
        # so its exact Shapley allocation is half to each participating feature.
        for j, k, weight in ((0, 1, 2.6), (2, 3, -2.1), (4, 6, 1.7), (5, 10, -1.4), (8, 9, 1.25)):
            share = weight * centered[j] * centered[k] / 2
            effects[j] += share
            effects[k] += share
        for (name, group, _), value, shap_value in zip(FEATURES, scaled, effects):
            yield sample, name, group, value, shap_value


def _xps_samples():
    rng = Random("xps-components")
    for step in range(401):
        energy = 282 + 10 * step / 400
        background = 1070 + 22 * (energy - 282) + 84 / (1 + exp(-(energy - 284.7) / 0.6))
        peaks = []
        for _, center, height, fwhm, fraction, _, _ in XPS_PEAKS:
            distance = 2 * (energy - center) / fwhm
            peaks.append(height * ((1 - fraction) * exp(-log(2) * distance**2) + fraction / (1 + distance**2)))
        envelope = background + sum(peaks)
        raw = round(envelope + rng.gauss(0, 0.48 * sqrt(envelope)) + 11 * cos(2 * pi * energy / 0.81))
        yield energy, raw, background, *peaks, envelope, raw - envelope


def write_advanced_inputs(directory):
    jobs = {
        "shap-summary": (("sample", "feature", "group", "scaled_value", "shap_value"), _shap_samples()),
        "xps-components": (("binding_energy_eV", "raw_counts", "background_counts", "cc_ch_counts",
                            "co_counts", "carbonyl_counts", "carboxyl_counts", "envelope_counts", "residual_counts"),
                           _xps_samples()),
    }
    for key, (fields, rows) in jobs.items():
        with (directory / f"{key}.csv").open("w", encoding="utf-8", newline="") as source:
            writer = csv.writer(source, lineterminator="\n")
            writer.writerow(fields)
            writer.writerows(tuple(f"{value:.10g}" if isinstance(value, float) else value for value in row) for row in rows)
