# KG Enhancement Method

## Objective

The goal of the KG enhancement step is to make the HPP food knowledge graph more
useful for biological interpretation and downstream prediction by weighting
edges according to how informative their target nodes are. The motivation is
that some nodes are connected to many foods and carry little food-specific
signal, whereas other nodes are selectively connected and may better summarize
distinctive chemical, metabolomic, disease, or pathway biology.

This is analogous to differential expression in transcriptomics: a feature is
more useful when it is selectively enriched relative to a background. It is also
related to entropy: nodes that are distributed broadly across many food
categories carry less specific information than nodes concentrated in a smaller
set of foods or food categories.

## Input Graph

The method uses the scenario-specific HPP knowledge graphs:

```text
outputs/enhanced_hpp/1.denovo/kg/hpp_scenario_kg_nodes.csv
outputs/enhanced_hpp/1.denovo/kg/hpp_scenario_kg_edges.csv
outputs/enhanced_hpp/2.nutrimatch_based/kg/hpp_scenario_kg_nodes.csv
outputs/enhanced_hpp/2.nutrimatch_based/kg/hpp_scenario_kg_edges.csv
```

The HPP food identifier remains the analysis unit. Canonical food concepts are
treated as helper nodes only.

## Metrics

Three weighting metrics are generated.

### 1. IDF

IDF is inverse food frequency. For each relation-target pair:

```text
IDF = log((N + 1) / (df + 1)) + 1
```

Where:

- `N` is the total number of HPP foods;
- `df` is the number of HPP foods connected to the target node through that
  relation.

Common nodes get weights close to 1. Selective nodes get higher weights.

### 2. IDF + Entropy

IDF alone measures global rarity but does not know whether a node is
concentrated in biologically meaningful food categories. Therefore, the second
metric adds food-category specificity.

For a target node:

```text
p(category | node) =
  number of foods in category connected to node /
  number of foods connected to node
```

Entropy:

```text
H(node) = -sum p(category | node) * log(p(category | node))
```

Normalized entropy:

```text
normalized_entropy = H(node) / log(number_of_categories)
```

Category specificity:

```text
specificity = 1 - normalized_entropy
```

Metric:

```text
IDF_entropy = IDF * specificity
```

This down-weights nodes spread broadly across food categories.

### 3. IDF + Entropy + Cross-Entropy Surprise

The third metric uses the cross-entropy idea by comparing each node's category
distribution with the background food-category distribution. In practice, the
most useful form is KL divergence, which is the difference between cross entropy
and entropy:

```text
KL(P_node || P_background) =
  sum P_node(category) *
      log(P_node(category) / P_background(category))
```

This measures how surprising or non-background-like the node's food-category
distribution is.

Metric:

```text
IDF_entropy_cross_entropy =
  IDF * specificity * log1p(KL(P_node || P_background))
```

This favors nodes that are:

- not connected to nearly every food;
- concentrated in fewer food categories;
- distributed differently from the background HPP food universe.

## Edge Weighting

For every edge:

```text
edge_base_value =
  numeric edge value, if present;
  otherwise 1

weighted_value =
  edge_base_value * node_information_weight
```

For nutrient amount edges, the base value is the per-100 g nutrient amount. For
annotation edges, the base value is 1 unless a source-specific numeric value is
available.

## Outputs

Run:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-kg-enhance
```

To rebuild one selected scenario/metric interactively:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-kg-enhance-interactive
```

Outputs are written under:

```text
outputs/KG_enhance/
```

For each scenario:

```text
outputs/KG_enhance/denovo/
outputs/KG_enhance/nutrimatch_based/
```

Node information score table:

```text
kg_node_information_scores.csv
```

For each metric:

```text
idf/
idf_entropy/
idf_entropy_cross_entropy/
```

Each metric folder contains:

```text
kg_weighted_edges_<metric>.csv.gz
kg_threshold_suggestions_<metric>.csv
kg_food_weighted_signature_matrix_<metric>.csv
kg_food_top_weighted_chemical_<metric>.csv
kg_food_top_weighted_metabolomics_<metric>.csv
kg_food_top_weighted_disease_<metric>.csv
kg_food_top_weighted_pathway_<metric>.csv
kg_weighting_summary_<metric>.json
```

The threshold explorer is:

```text
outputs/KG_enhance/kg_weighting_threshold_explorer.html
```

## Threshold Selection

For each metric, the pipeline evaluates weighted-value thresholds at several
quantiles:

```text
50%, 75%, 90%, 95%, 97.5%, 99%
```

The suggested threshold favors aggressive edge reduction while retaining broad
food coverage and a usable median number of retained edges per food. These
thresholds are not final biological truth; they are starting points for
inspection and downstream prediction comparison.

## Recommended Evaluation

Evaluate the three metrics by checking:

1. whether ubiquitous nodes move down in rank;
2. whether known foods retain meaningful signals, for example coffee retaining
   caffeine-related chemical/pathway evidence;
3. whether the top weighted food-category signatures are biologically plausible;
4. whether thresholded graphs are easier to visualize;
5. whether TRE-side prediction improves or becomes more stable compared with
   unweighted KG features.
