# Generate R-side canonicalised name-count baselines for tests/test_snapshot.py.
#
# This is a one-off script — run under ggrepel-dev when we intentionally
# want to refresh the R gold.  Its output files (``tests/_snapshots/*.tsv``)
# are committed to git so ``test_snapshot.py`` can load them without
# invoking R at test time.
#
# Canonicalisation folds R-specific names onto the names ``ggplot2_py`` /
# ``patchwork-python`` emit (e.g. ``guide-box-right`` → ``guide-box``,
# ``axis-b-1-1`` → ``axis-b``).  The test then compares *counts* of
# canonical names — a coarse-but-robust fingerprint that survives the
# minor positional differences between R and Python after add_strips
# brings both to the canonical 18xN shape.
#
# Run:
#   Rscript tests/_snapshots/gen_gold.R

suppressPackageStartupMessages({
  library(patchwork)
  library(ggplot2)
})

script_dir <- "tests/_snapshots"
if (!dir.exists(script_dir)) {
  dir.create(script_dir, showWarnings = FALSE, recursive = TRUE)
}

# Deterministic toy data (no mtcars — keeps fixtures cheap and language-agnostic).
df <- data.frame(x = 1:4, y = c(1, 3, 2, 4))
p1 <- ggplot(df) + geom_point(aes(x, y))
p2 <- ggplot(df) + geom_point(aes(x, y))
p3 <- ggplot(df) + geom_point(aes(x, y))
p4 <- ggplot(df) + geom_point(aes(x, y))

# -- Name-canonicalisation (mirror validation/_diff_helpers.py::canonical_name) --
canonical <- function(name) {
  n <- name
  # panel-a; panel-1-1... → panel
  if (startsWith(n, "panel;")) return("panel")
  # Compound names from R's paste(..., collapse=", ") → take first component.
  if (grepl(", ", n)) {
    n <- strsplit(n, ", ")[[1]][1]
  }
  # Strip trailing -N or -N-N
  n <- sub("-\\d+(-\\d+)*$", "", n)
  # R directional synonyms → Py canonical
  syn <- list(
    "xlab-t" = "xlab", "xlab-b" = "xlab",
    "ylab-l" = "ylab", "ylab-r" = "ylab",
    "guide-box-right" = "guide-box", "guide-box-left" = "guide-box",
    "guide-box-top" = "guide-box", "guide-box-bottom" = "guide-box",
    "guide-box-inside" = "guide-box",
    # Directional axes — emit only if non-empty after canonicalisation
    "axis-r" = "axis-r-only-in-r", "axis-t" = "axis-t-only-in-r",
    "spacer" = "spacer-only-in-r", "subtitle" = "subtitle-only-in-r",
    "caption" = "caption-only-in-r",
    "free_panel" = "free_panel-only-in-r",
    "free_row" = "free_row-only-in-r",
    "free_col" = "free_col-only-in-r",
    "patchwork-table" = "patchwork-table-only-in-r",
    # Structural decorations filtered on both sides (see test_snapshot.py).
    "background" = "background-decoration-ignored",
    "panel-area" = "background-decoration-ignored"
  )
  if (!is.null(syn[[n]])) n <- syn[[n]]
  n
}

`%||%` <- function(a, b) if (is.null(a)) b else a

dump_counts <- function(pw, tag) {
  gt <- patchworkGrob(pw)
  names_raw <- gt$layout$name
  # Drop zeroGrob-like layout entries so counts reflect present content only.
  not_zero <- vapply(gt$grobs, function(g) {
    !(is.null(g) || inherits(g, "zeroGrob") || (inherits(g, "gtable") && length(g$grobs) == 0))
  }, logical(1))
  names_present <- names_raw[not_zero]
  canons <- vapply(names_present, canonical, character(1))
  # Ignore R-only placeholders and cross-platform structural decorations.
  canons <- canons[!grepl("-only-in-r$|-decoration-ignored$", canons)]
  tab <- table(canons)
  ord <- sort(names(tab))
  lines <- vapply(ord, function(n) sprintf("%s\t%d", n, tab[[n]]), character(1))
  path <- file.path(script_dir, paste0(tag, ".tsv"))
  writeLines(lines, path)
  cat(sprintf("Wrote %s: %d canonical names\n", path, length(lines)))
}

# -- Fixtures — cover the core composition paths --
dump_counts(p1 + p2,                                    "two_plus")
dump_counts(p1 / p2,                                    "two_stack")
dump_counts(wrap_plots(list(p1, p2, p3, p4)),           "wrap_four")
dump_counts(p1 + (p2 + p3),                             "nested")
dump_counts(
  p1 + p2 + p3 + plot_layout(design = "AA#\nBCC"),
  "design_string"
)
dump_counts(
  (p1 + p2) + plot_annotation(title = "Hello", subtitle = "Sub"),
  "annotated"
)

# With tag_levels — added after #32 closed (ggplot2_py now emits the
# `tag` layout row via _table_add_tag; has_tag.Patchwork propagates
# through to the active plot during recurse_tags).
dump_counts(
  (p1 + p2 + p3) + plot_annotation(tag_levels = "A"),
  "tagged"
)
