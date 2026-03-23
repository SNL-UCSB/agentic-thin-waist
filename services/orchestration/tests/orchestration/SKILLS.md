# Available Skills for Multi-Step Workflows

## parameter_sweep
Run experiments across parameter ranges (Cartesian expansion).
Input:
- applications
- capacity_range or capacity_values
- latency_range or latency_values
- cc_algorithms (optional)
- aqm_policy (optional)
- duration_seconds (optional)
- num_trials (optional)

## application_comparison
Compare applications under one shared network configuration.
Input:
- applications
- capacity_mbps
- latency_ms
- cc_algorithm (optional)
- aqm_policy (optional)
- duration_seconds (optional)

## baseline_establishment
Establish ideal-network baselines for selected applications.
Input:
- applications
- duration_seconds (optional)
- num_trials (optional)

## network_characterization
Factorial characterization over explicit capacity and latency vectors.
Input:
- applications
- capacity_values
- latency_values
- cc_algorithms (optional)
- aqm_policy (optional)

## replicate_study
Recreate a known matrix from previously published study settings.
Input:
- study_name
- matrix
- num_trials (optional)

