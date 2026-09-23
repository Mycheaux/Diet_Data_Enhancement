# Nitrate Vascular Aging Paper Concept

## Working Title

Emulating A Vegetable-Nitrate Dietary Intervention For Oral Microbiome Remodeling And Blood Pressure Regulation In Vascular Aging

## Abstract

Ageing is associated with reduced nitric oxide bioavailability, vascular stiffening, and increasing blood pressure. Dietary nitrate from vegetables can enter the enterosalivary nitrate cycle, where oral bacteria reduce nitrate to nitrite, enabling downstream nitric oxide production and vascular relaxation. Controlled nitrate supplementation studies suggest that older adults may derive greater blood-pressure benefit from nitrate intake than younger adults, partly through oral microbiome remodeling, including increased Neisseria/Rothia and decreased Prevotella/Veillonella-like taxa. However, it remains unclear whether habitual nitrate-rich dietary patterns in a large free-living population are associated with similar age-dependent oral microbiome and blood-pressure signatures.

We propose a target-trial-emulation and intervention-simulation analysis in HPP to estimate the expected effect of increasing vegetable-nitrate-rich foods on oral nitrate-cycle microbiome balance and blood-pressure phenotypes, with particular focus on older adults. Knowledge-graph-enhanced dietary phenotyping will distinguish vegetable nitrate from processed nitrite, nitroso-related foods, and arginine/nitric-oxide-axis foods. Oral microbiome features will be summarized using a nitrate-balance score contrasting Neisseria/Rothia-like nitrate-cycle taxa against Prevotella/Veillonella/Megasphaera-like anaerobic taxa. The primary clinical outcomes will be systolic and diastolic blood pressure, with secondary outcomes including hypertension status, cardiometabolic biomarkers, and inflammation markers where available.

The central hypothesis is that older adults show a stronger vegetable-nitrate-associated shift away from Prevotella/Veillonella-dominant oral communities and toward a nitrate-cycle-compatible oral microbiome, and that this microbial shift is associated with lower blood pressure or better vascular-risk profiles. If supported, this would suggest that age-related vascular nitrate responsiveness can be detected from habitual diet and oral microbiome data, motivating earlier dietary nitrate optimization for blood-pressure regulation and vascular ageing prevention.

## Clinical Idea

The paper is not only about diet and microbiome. The clinical question is:

Can we identify people, especially older adults, who may benefit most from increasing vegetable-nitrate-rich foods for blood-pressure regulation because of their oral microbiome state?

## Proposed Causal / Target-Trial Frame

### Eligibility

- HPP participants with:
  - diet logging
  - oral microbiome
  - age and sex
  - BMI
  - smoking/alcohol data if available
  - blood pressure measurements if available

- Consider excluding or stratifying:
  - antihypertensive medication users
  - recent antibiotic users
  - severe chronic disease if relevant
  - poor timing alignment between diet, microbiome, and BP measurements

### Intervention Strategies

- High vegetable nitrate exposure
- Low vegetable nitrate exposure
- Processed nitrite as a contrast exposure
- Nitroso axis as a risk-context contrast

### Primary Outcome

- Systolic blood pressure
- Diastolic blood pressure

### Secondary Outcomes

- Hypertension status
- Pulse pressure if available
- Lipids
- glucose / HbA1c
- inflammatory markers such as CRP or GlycA if available
- vascular/metabolic age-related phenotypes

### Mediator / Mechanistic Feature

Oral nitrate-balance score:

```text
log1p(Neisseria + Rothia)
-
log1p(Prevotella + Veillonella + Megasphaera)
```

Alternative scores:

```text
beneficial_nitrate_score = Neisseria + Rothia + Haemophilus + Kingella
anaerobic_dysbiosis_score = Prevotella + Veillonella + Megasphaera
nitrate_balance = beneficial_nitrate_score - anaerobic_dysbiosis_score
```

## Core Models

### Diet To Oral Microbiome

```text
oral_nitrate_balance ~ vegetable_nitrate + age + vegetable_nitrate:age
                     + sex + BMI + smoking + alcohol
```

Expected:

- vegetable nitrate increases nitrate balance
- vegetable nitrate decreases Prevotella / Veillonella
- age amplifies the vegetable-nitrate effect

### Diet To Blood Pressure

```text
systolic_bp ~ vegetable_nitrate + age + vegetable_nitrate:age
            + sex + BMI + smoking + alcohol
```

Expected:

- high vegetable nitrate is associated with lower BP, especially in older participants

### Microbiome To Blood Pressure

```text
systolic_bp ~ oral_nitrate_balance + age + oral_nitrate_balance:age
            + vegetable_nitrate + sex + BMI + smoking + alcohol
```

Expected:

- higher nitrate balance is associated with lower BP
- association may be stronger in older adults

### Mediation-Style Analysis

```text
vegetable_nitrate -> oral_nitrate_balance -> systolic_bp
```

This should be framed as mediation-style observational evidence, not definitive causal mediation unless assumptions and timing are strong.

## Intervention Simulation

After fitting models, simulate:

- moving low vegetable nitrate participants to a high vegetable nitrate exposure level
- predicted change in oral nitrate balance
- predicted change in systolic/diastolic BP
- effect by age decile
- effect by baseline oral microbiome responder class

Possible output:

- predicted SBP benefit in older high-responder group
- predicted SBP benefit in younger participants
- predicted benefit among low baseline nitrate-balance participants
- contrast with processed nitrite exposure

## Why This Could Be NEJM-Like

- Hypertension and vascular ageing are major clinical problems.
- Vegetable nitrate is cheap, scalable, and modifiable.
- Oral microbiome provides a measurable mechanism.
- Age-specific targeting could make the intervention clinically actionable.
- HPP enables population-scale analysis of habitual diet, oral microbiome, and clinical phenotypes.

The NEJM-like clinical claim would be:

Older adults may be more responsive to vegetable nitrate because nitrate-related oral microbiome remodeling restores nitric-oxide biology and supports blood-pressure regulation.

## What Would Be Needed For A Very Strong Paper

- Clear BP phenotype with timing relative to diet and oral microbiome.
- Medication handling, especially antihypertensives.
- Strong adjustment for confounding.
- Processed nitrite negative/contrast exposure.
- Sensitivity analyses by smoking, alcohol, BMI, sex, and baseline BP.
- Ideally longitudinal BP or incident hypertension.
- External validation or replication if available.

## Key Risk

NEJM would not be persuaded by AI/KG novelty alone. The AI-enhanced dietary phenotyping should be framed as an enabling method. The main claim must be clinical:

age-specific dietary nitrate responsiveness, oral microbiome remodeling, and blood-pressure regulation.

