# QUEUE_SIM

# QUEUE_SIM record

S1 go/no-go = replay edge, NOT queue fill%. Low fill% on short L2 = calibrate, don't kill S1.

| scenario | label | fill_ratio | n_rest | hidden | latency |
|---|---|---:|---:|---:|---:|
| base | plan | 0.1014 | 69 | 1.25 | 1 |
| pessimistic | stress | 0.0725 | 69 | 1.6 | 2 |
| optimistic | upper_bound_only | 0.1159 | 69 | 1.0 | 0 |

size_ok=false. Optimistic is upper bound only, not for sizing.

# QUEUE_SIM tape_bosona

S1 go/no-go = replay edge, NOT queue fill%. Low fill% on short L2 = calibrate, don't kill S1.

| scenario | label | fill_ratio | n_rest | hidden | latency |
|---|---|---:|---:|---:|---:|
| base | plan | 0.3650 | 84 | 1.25 | 1 |
| pessimistic | stress | 0.1901 | 84 | 1.6 | 2 |
| optimistic | upper_bound_only | 0.9125 | 84 | 1.0 | 0 |

size_ok=false. Optimistic is upper bound only, not for sizing.

