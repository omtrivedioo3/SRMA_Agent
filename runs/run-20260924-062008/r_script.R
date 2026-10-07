# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20260924-062008
# Outcome: All-cause mortality
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

m_data <- data.frame(
  study   = c("Hospital (2022). PMID:41456635", "Moller et al. (2021). PMID:7053293", "Hospital (2021)", "Paris et al. (2023). NCT05764057", "Toronto et al. (2018). NCT03416270", "University et al. (2016). PMID:29603546"),
  event_e = c(150, 5, 100, 100, 12, 169),
  n_e     = c(3000, 100, 1000, 1000, 100, 4733),
  event_c = c(150, 6, 110, 110, 15, 183),
  n_c     = c(3000, 100, 1000, 1000, 100, 4733)
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