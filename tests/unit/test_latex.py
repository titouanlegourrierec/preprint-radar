import pytest

from preprint_radar.latex import plain_text


@pytest.mark.parametrize(
    ("abstract", "plain"),
    [
        pytest.param(
            r"we propose \textbf{GestureFAR}, a \emph{flow} framework",
            "we propose GestureFAR, a flow framework",
            id="text-macros",
        ),
        pytest.param(r"Code: \url{https://github.com/a/b}.", "Code: https://github.com/a/b.", id="url"),
        pytest.param(
            r"at \href{https://x.org/a}{here} and \href{https://x.org/b}{\texttt{https://x.org/b}}",
            "at here (https://x.org/a) and https://x.org/b",
            id="href",
        ),
        pytest.param(r"see \textcolor{blue}{here}", "see here", id="color"),
        pytest.param(
            r"Homepage: \href{https://x.org}, 45 km\textsuperscript{2}, at {\small{https://y.org}}",
            "Homepage: https://x.org, 45 km\N{SUPERSCRIPT TWO}, at https://y.org",
            id="href-alone-superscripts-switches",
        ),
        pytest.param(
            r"RaTEScore~\cite{zhao2024} decrease, as before \citep[p. 2]{roe}.",
            "RaTEScore decrease, as before.",
            id="citations",
        ),
        pytest.param(
            r"the cost ({\em e.g.}, speed), `{\it events}'", "the cost (e.g., speed), `events'", id="groups"
        ),
        pytest.param(
            r"(from $\sim$18--20\% to $\sim$3--6\%)",
            "(from ~18\N{EN DASH}20% to ~3\N{EN DASH}6%)",
            id="percents",
        ),
        pytest.param(r"at 1 m/10$^\circ$ and ($\ge 27^{\circ}$C)", "at 1 m/10° and (≥27°C)", id="degrees"),
        pytest.param(
            r"($12.5\!\to\!5.5$ mm), $\Delta V$, $\rho=0.64$",
            "(12.5→5.5 mm), ΔV, \N{GREEK SMALL LETTER RHO}=0.64",
            id="symbols",
        ),
        pytest.param(
            r"the torus $S^2\times S^1$ in $\mathcal{O}(d^3)$",
            "the torus $S^2\N{MULTIPLICATION SIGN}S^1$ in $O(d^3)$",
            id="markup-stays",
        ),
        pytest.param(r"$1/\sqrt{K}$ and $\sqrt{2N}$", "1/√K and √(2N)", id="roots"),
        pytest.param(
            r"B$\acute{\rm e}$zier, Schr\"odinger, \'{E}cole", "Bézier, Schrödinger, École", id="accents"
        ),
        pytest.param(r"PURGE (\underline{P}artition-aware)", "PURGE (Partition-aware)", id="underline"),
        pytest.param(r"Approach\footnote{Code soon.} works", "Approach (Code soon.) works", id="footnote"),
        pytest.param(
            r"we introduce \method, \ie, an agent (\eg, LIBERO) by Doe \etal and",
            "we introduce \\method, i.e., an agent (e.g., LIBERO) by Doe et al. and",
            id="words",
        ),
        pytest.param(
            r"$\unicode{x1F493}$Heartian costs \$5 \& more",
            "\N{BEATING HEART}Heartian costs $5 & more",
            id="escapes",
        ),
        pytest.param(r"efficiency---gains, \(k\) grows", "efficiency\N{EM DASH}gains, k grows", id="dashes"),
        pytest.param(
            r"an {8$\times$} speedup, at {$64\times64$}, {i.e., GTA5 $\rightarrow$ Cityscapes}",
            "an 8\N{MULTIPLICATION SIGN} speedup, at 64\N{MULTIPLICATION SIGN}64, "
            "i.e., GTA5 \N{RIGHTWARDS ARROW} Cityscapes",
            id="group-of-a-formula",
        ),
        pytest.param(
            # Plain already, as `make venues` reads stored abstracts: prices, not formulas.
            "saving nearly $300,000 ($26,000 vs. $320,000), at $5.95 per subject, or $8.38",
            "saving nearly $300,000 ($26,000 vs. $320,000), at $5.95 per subject, or $8.38",
            id="prices",
        ),
        pytest.param("SLAug . Spaces  stay\nwritten", "SLAug . Spaces stay written", id="spaces"),
        pytest.param(r"\textbf{unclosed and \url", r"\textbf{unclosed and \url", id="malformed"),
        pytest.param(
            r"\textcolor{blue} and \href and \cite[p. 2 and \emph alone",
            r"\textcolor{blue} and \href and \cite[p. 2 and \emph alone",
            id="arguments-missing",
        ),
    ],
)
def test_plain_text(abstract: str, plain: str) -> None:
    assert plain_text(abstract) == plain
    # `make venues` reads the stored abstracts again: plain text stays as it is.
    assert plain_text(plain) == plain
