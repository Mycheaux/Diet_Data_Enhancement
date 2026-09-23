# Manual Exploratory Analyses

This folder contains TRE-side exploratory notebooks that are not part of the
main automated benchmark runners.

## Diet And Mental Health

Notebook:

```text
diet-mental_health.ipynb
```

Purpose:

- estimate participant-level dietary exposure to selected chemicals using diet
  logs plus Diet Data Enhancement food/KG tables;
- assign low/mid/high exposure groups;
- load mental-health survey metrics from
  `PhenoLoader("psychological_and_social_health")`;
- test group differences with Kruskal-Wallis and pairwise Mann-Whitney tests;
- create heatmaps and boxplots with p-values/FDR q-values.

The notebook is exploratory and should not be interpreted causally without
confounder adjustment and stronger temporal design.
