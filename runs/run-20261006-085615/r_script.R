# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20261006-085615
# Outcome: Major adverse cardiovascular events (MACE: cardiovascular death, nonfatal myocardial infarction, or nonfatal stroke)
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

m_data <- data.frame(
  study   = c("Tobaiqy et al. (2024). PMID:38265519"),
  event_e = c(187),
  n_e     = c(13956),
  event_c = c(144),
  n_c     = c(16748)
)

# Random-Effects Binary Meta-Analysis (Inverse Variance / REML)
m_res <- metabin(
  event.e = event_e, n.e = n_e,
  event.c = event_c, n.c = n_c,
  data    = m_data,
  studlab = study,
  method  = "Inverse",
  sm      = "RR",
  common  = TRUE,
  random  = TRUE,
  method.tau = "REML",
  hakn    = TRUE
)

summary(m_res)
forest(m_res, layout = "Cochrane", col.square = "navy", prediction = TRUE, print.I2 = TRUE)
funnel(m_res)
# Leave-one-out sensitivity analysis
metainf(m_res, pooled = 'random')