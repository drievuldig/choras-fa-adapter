# Sample CHORAS Input

Use `choras_input.example.json` as a starting point for local adapter runs.

Before running:

1. Replace `msh_path` with a real `.msh` path.
2. Ensure `absorption_coefficients` keys match physical-group boundary names in the mesh.
   Values can be comma-separated strings (`"0.6, 0.69, 0.71"`) or numeric vectors.
3. Ensure `simulationSettings` includes required FA fields:
	`fa_c0_mps`, `fa_rho0_kgpm3`, `fa_ir_length_s`, `fa_max_gridstep_cm`, `fa_freq_limit_hz`.
4. Ensure frequency bands are provided under `results[*].frequencies` (CHORAS shape).
5. Set required runtime environment variables (`CHORAS_FA_BASE_URL` and token source).

Run:

```bash
choras-fa-adapter run --json samples/choras_input.example.json
```
