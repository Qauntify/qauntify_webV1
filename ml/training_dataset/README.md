# Training Dataset Builder (`training_v1`)

`training_v1` performs an exact one-to-one join of immutable `feature_v1` and
`outcome_v1` rows by `candidate_id`. Model inputs are explicitly listed in the
manifest and come only from the signal-time feature dataset. Future-derived
fields are isolated as targets or target metadata.

Targets are the original multiclass `outcome_class`, regression
`net_realized_r`, and binary success where `net_realized_r > 0`. Zero and
negative R are failures. Right-censored candidates remain in the dataset for
coverage auditing but their regression/binary targets are null and they are not
eligible for supervised fitting.

## Temporal isolation

The main split is chronological by candidate timestamp: 70% train, 15%
validation, and 15% test boundary positions. A 14-calendar-day embargo is
removed before validation and test, matching the longest `outcome_v1` horizon.
Label-window purging additionally removes any earlier row whose
`resolution_timestamp` reaches the next split start. Equal timestamps never
cross a boundary because assignment is timestamp-based.

Five expanding walk-forward folds start with 50% history and use the next 10%
as validation. Each fold applies the same 14-day embargo and label-window purge.
No random splitting, feature selection, fitting, or tuning occurs here.
