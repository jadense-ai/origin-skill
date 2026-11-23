"""Deterministic synthetic inputs for the sixteen native Origin showcase plots."""

import csv
from cmath import tanh
from math import cos, exp, log, pi, sin, sqrt
from pathlib import Path
from random import Random
from statistics import mean, pstdev


AXIS_TITLES = {
    "heatmap": ("Condition", "Feature"),
    "multi-panel": ("Time (s)", "Signal (a.u.)"),
    "xrd-stack": ("2θ (°)", "Offset intensity (a.u.)"),
    "eis-nyquist": ("Z′ (Ω)", "−Z″ (Ω)"),
    "violin": ("Treatment", "Response (a.u.)"),
    "box-raw": ("Condition–cohort", "Normalized response"),
    "histogram": ("Latency (ms)", "Count"),
    "ecdf": ("Recovery time (s)", "Cumulative fraction"),
    "dose-response": ("Dose (µM)", "Activity (%)"),
    "grouped-column": ("Material", "Yield (%)"),
    "event-study": ("Months from event", "Change (pp)"),
    "coefficient-interval": ("Standardized effect", "Predictor"),
    "multi-line": ("Wavelength (nm)", "Absorbance (a.u.)"),
    "scatter": ("Leaf length (cm)", "Leaf width (cm)"),
    "dual-y": ("Elapsed time (h)", "Temperature (°C)", "Relative humidity (%)"),
    "likert": ("Survey item", "Share of responses (%)"),
}


def _heatmap(rng):
    # Three feature modules respond differently to three condition blocks.
    effects = ((1.15, -0.68, 0.31), (-0.42, 1.12, -1.15), (-1.06, 0.35, 1.30))
    # Origin's matrix Y axis increases from the bottom, so F01 is written last.
    for row in range(29, -1, -1):
        responses = []
        for col in range(30):
            block = effects[row // 10][col // 10]
            ridge = 1.05 * exp(-0.5 * ((col - row - 2) / 3.2) ** 2)
            wave = 0.36 * sin(row * 0.41 + col * 0.67) + 0.32 * cos(col * 0.34 - row * 0.15)
            responses.append(block + ridge + wave + rng.gauss(0, 0.13))
        center, scale = mean(responses), pstdev(responses)
        for col, value in enumerate(responses, 1):
            yield f"F{row + 1:02d}", f"C{col:02d}", (value - center) / scale


def _multi_panel(rng):
    # Four gains applied to a pulse pair with a shorter second drive.
    # PAN2VERT places the second recipe layer above the first.
    drive_rows = []
    for group, gain, tau in (("Gain 1", 0.35, 2.6), ("Gain 2", 0.55, 3.3),
                             ("Gain 3", 0.77, 4.4), ("Gain 4", 1.00, 5.6)):
        response = 0.0
        response_step = 1 - exp(-0.125 / tau)
        for step in range(-32, 249):
            t = step / 8
            first = 1 / (1 + exp(-6 * t)) - 1 / (1 + exp(-6 * (t - 8)))
            second = 1 / (1 + exp(-6 * (t - 15))) - 1 / (1 + exp(-6 * (t - 19)))
            drive = gain * (first + 0.76 * second)
            response += (drive - response) * response_step
            yield "Response", group, t, response + rng.gauss(0, 0.006)
            drive_rows.append(("Drive", group, t, drive + rng.gauss(0, 0.008)))
    yield from drive_rows


def _xrd(rng):
    centers = (20.7, 26.7, 29.5, 32.3, 35.1, 37.9, 43.4, 47.9, 53.8, 59.7, 64.1, 69.6, 75.3, 80.2)
    patterns = (
        ("As grown", 0.00, 0.21, (0.33, 1.00, 0.08, 0.24, 0.49, 0.18, 0.69, 0.19, 0.34, 0.09, 0.44, 0.17, 0.13, 0.10)),
        ("Annealed", -0.09, 0.16, (0.12, 0.89, 0.17, 0.29, 0.61, 0.10, 1.00, 0.24, 0.45, 0.12, 0.43, 0.27, 0.24, 0.15)),
        ("Quenched", 0.13, 0.28, (0.26, 0.73, 0.23, 0.55, 0.24, 0.21, 1.00, 0.37, 0.34, 0.30, 0.15, 0.38, 0.32, 0.08)),
        ("Reheated", 0.02, 0.19, (0.15, 0.91, 0.12, 0.32, 0.70, 0.13, 0.88, 0.34, 0.40, 0.19, 0.33, 0.22, 0.22, 0.11)),
    )
    for sample, shift, width, amplitudes in patterns:
        for step in range(1201):
            theta = 14 + step * 0.06
            background = 0.02 + 0.08 * exp(-(theta - 14) / 23)
            peaks = 0.0
            for center, amplitude in zip(centers, amplitudes):
                d = (theta - center - shift) / (width + 0.0018 * (center - centers[0]))
                peaks += amplitude * (0.72 * exp(-0.5 * d * d) + 0.28 / (1 + d * d))
            yield sample, theta, background + peaks + rng.gauss(0, 0.003 + 0.006 * sqrt(peaks))


def _eis(rng):
    # Series resistance, two depressed arcs, and finite-length diffusion.
    for sample, resistance, fast, slow, diffusion in (
        ("Fresh", 5.0, 23, 9, 15), ("Conditioned", 6.2, 29, 13, 21),
        ("Aged", 9.8, 45, 21, 35), ("Recovered", 7.4, 36, 15, 25),
    ):
        for step in range(85):
            frequency = 10 ** (4 - step / 14)
            jw = 2j * pi * frequency
            fast_arc = fast / (1 + (jw * 0.0018) ** 0.87)
            slow_arc = slow / (1 + (jw * 0.13) ** 0.78)
            diffusion_arg = (jw * 54) ** 0.5
            impedance = resistance + fast_arc + slow_arc + diffusion * tanh(diffusion_arg) / diffusion_arg
            sd = 0.015 + 0.002 * abs(impedance.imag)
            impedance += complex(rng.gauss(0, sd), rng.gauss(0, sd))
            yield sample, frequency, impedance.real, impedance.imag


def _violin(rng):
    for group, size, lower, upper, lower_share in (
        ("Control", 96, (32, 4.5), (40, 4.5), 0.70), ("Low", 110, (37, 4.8), (49, 5.7), 0.40),
        ("Mid", 120, (42, 4.1), (61, 3.8), 0.42), ("High", 112, (55, 5.4), (64, 3.7), 0.30),
        ("Washout", 94, (39, 6.0), (53, 5.4), 0.65),
    ):
        for _ in range(size):
            value = rng.gauss(*(lower if rng.random() < lower_share else upper))
            yield group, value


def _box(rng):
    for condition, (a_median, b_median, a_width, b_width) in enumerate((
        (0.98, 0.99, 0.08, 0.10), (1.03, 1.14, 0.09, 0.10),
        (1.11, 1.29, 0.09, 0.12), (1.20, 1.43, 0.11, 0.13),
    )):
        size = 20 + 2 * condition
        for cohort, count, median, width in (("A", size, a_median, a_width), ("B", size + 2, b_median, b_width)):
            for _ in range(count):
                yield f"C{condition}-{cohort}", rng.lognormvariate(log(median), width)


def _histogram(rng):
    for _ in range(960):
        component = rng.random()
        center, width = (51, 6.5) if component < 0.54 else (83, 9.0) if component < 0.88 else (118, 10.5)
        yield (rng.gauss(center, width),)


def _ecdf(rng):
    for group, size, median, width in (("Control", 180, 22, 0.39), ("Fast path", 160, 13, 0.44),
                                       ("Adaptive", 200, 17, 0.29), ("Fallback", 175, 19, 0.56)):
        for _ in range(size):
            yield group, rng.lognormvariate(log(median), width)


def _dose_response(rng):
    doses = (0, 0.75, 1.5, 2.5, 4, 5.5, 7.5, 10, 13, 16, 20, 25, 31, 38, 46)
    for sample, lower, upper, midpoint, hill in (
        ("Assay A", 5, 97, 4.8, 1.70), ("Assay B", 10, 96, 11.7, 2.15), ("Assay C", 21, 95, 20.0, 2.60),
    ):
        offsets = [rng.gauss(0, 1.1) for _ in range(8)]
        for dose in doses:
            remaining = lower + (upper - lower) / (1 + (dose / midpoint) ** hill)
            for offset in offsets:
                yield sample, dose, min(100, max(0, remaining + offset + rng.gauss(0, 2.5)))


def _grouped_column(_rng):
    for material, yields in (("Al", (56, 73, 88, 91)), ("Cu", (68, 77, 83, 76)),
                             ("Fe", (51, 64, 60, 78)), ("Ni", (36, 58, 78, 88)),
                             ("Ti", (65, 72, 68, 74)), ("Zn", (51, 62, 72, 67))):
        for method, value in zip(("Method A", "Method B", "Method C", "Method D"), yields):
            yield material, method, value


def _event_study(_rng):
    # Relative period -1 is the omitted baseline.
    periods = (*range(-10, -1), *range(11))
    estimates = (-0.2, 0.4, 0.3, -0.1, -0.4, 0.3, 0.1, -0.2, 0.2,
                 1.1, 2.6, 3.8, 4.7, 5.2, 5.6, 5.4, 5.1, 4.7, 4.3, 3.9)
    for month, estimate in zip(periods, estimates):
        half_width = 0.62 + 0.26 * sqrt(abs(month) + 1) + 0.10 * cos(month * 1.1)
        yield month, estimate, estimate - half_width, estimate + half_width


def _coefficients(_rng):
    yield from (
        ("Salinity", -.44, -.61, -.27),
        ("Turbidity", -.32, -.48, -.16),
        ("Depth", -.21, -.41, -.01),
        ("Flow", -.17, -.31, -.03),
        ("Conductivity", -.08, -.23, .07),
        ("Alkalinity", .02, -.17, .21),
        ("Nitrate", .13, -.02, .28),
        ("Phosphate", .22, .03, .41),
        ("Dissolved O2", .30, .16, .44),
        ("Temperature", .39, .19, .59),
        ("Light", .51, .35, .67),
    )


def _spectra(rng):
    # Synthetic components are shown from zero; the envelope adds the separate baseline.
    peaks = (("Peak I", 429, .58, 20), ("Peak II", 491, .67, 28),
             ("Peak III", 552, .81, 33), ("Peak IV", 623, .43, 37))
    series = (*[peak[0] for peak in peaks], "Baseline", "Model", "Observed")
    spectra = {name: [] for name in series}
    for wavelength in range(380, 741):
        baseline = .030 + .00010 * (wavelength - 380) + .055 * exp(-(wavelength - 380) / 58)
        model = baseline
        for name, center, amplitude, width in peaks:
            value = amplitude * exp(-.5 * ((wavelength - center) / width) ** 2)
            spectra[name].append((wavelength, value))
            model += value
        spectra["Baseline"].append((wavelength, baseline))
        spectra["Model"].append((wavelength, model))
        if wavelength % 2 == 0:
            residual = .008 * sin(wavelength / 7) + rng.gauss(0, .005 + .009 * model)
            spectra["Observed"].append((wavelength, model + residual))
    for name, values in spectra.items():
        for wavelength, value in values:
            yield name, wavelength, value


def _scatter(rng):
    for group, size, mean_length, length_sd, intercept, slope in (
        ("Species A", 92, 4.0, .71, .15, .43), ("Species B", 108, 5.4, .94, .74, .42),
        ("Species C", 96, 6.8, .96, .16, .48), ("Species D", 88, 7.7, .91, 1.35, .44),
    ):
        for _ in range(size):
            length = rng.gauss(mean_length, length_sd)
            width = intercept + slope * length + rng.gauss(0, .15 + .022 * length)
            yield group, length, width


def _dual_y(rng):
    for step in range(97):
        hour = step / 2
        cloud = 2.8 * exp(-0.5 * ((hour - 38.4) / 2.2) ** 2)
        temperature = 18 + 6.4 * cos(2 * pi * (hour - 15) / 24) - cloud + 0.04 * hour
        temperature += 0.55 * sin(2 * pi * hour / 12) + rng.gauss(0, 0.19)
        humidity = 72 - 15.3 * cos(2 * pi * (hour - 16.5) / 24) + 4.4 * cloud + rng.gauss(0, 0.75)
        yield hour, temperature, humidity


def _likert(_rng):
    for item, counts in (
        ("Clarity", (4, 13, 29, 55, 79)),
        ("Access", (8, 18, 27, 57, 70)),
        ("Speed", (13, 29, 39, 58, 41)),
        ("Support", (24, 32, 38, 50, 36)),
        ("Accuracy", (25, 30, 55, 45, 24)),
        ("Coverage", (28, 40, 41, 43, 24)),
        ("Training", (45, 47, 38, 34, 12)),
        ("Updates", (61, 42, 32, 28, 10)),
    ):
        for rating, count in enumerate(counts, 1):
            yield item, rating, count


INPUTS = {
    "heatmap": (("row", "column", "value"), _heatmap),
    "multi-panel": (("panel", "series", "x", "y"), _multi_panel),
    "xrd-stack": (("sample", "two_theta", "intensity"), _xrd),
    "eis-nyquist": (("sample", "frequency", "z_real", "z_imag"), _eis),
    "violin": (("group", "value"), _violin),
    "box-raw": (("group", "value"), _box),
    "histogram": (("value",), _histogram),
    "ecdf": (("group", "value"), _ecdf),
    "dose-response": (("series", "dose", "response"), _dose_response),
    "grouped-column": (("category", "series", "value"), _grouped_column),
    "event-study": (("period", "estimate", "lower", "upper"), _event_study),
    "coefficient-interval": (("term", "estimate", "lower", "upper"), _coefficients),
    "multi-line": (("series", "x", "y"), _spectra),
    "scatter": (("series", "x", "y"), _scatter),
    "dual-y": (("x", "left", "right"), _dual_y),
    "likert": (("item", "rating", "count"), _likert),
}


def write_inputs(directory):
    """Write recipe-compatible CSVs without external data or dependencies."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for recipe, (fields, rows) in INPUTS.items():
        with (directory / f"{recipe}.csv").open("w", encoding="utf-8", newline="") as source:
            writer = csv.writer(source, lineterminator="\n")
            writer.writerow(fields)
            for row in rows(Random(recipe)):
                writer.writerow(f"{value:.8g}" if isinstance(value, float) else value for value in row)
