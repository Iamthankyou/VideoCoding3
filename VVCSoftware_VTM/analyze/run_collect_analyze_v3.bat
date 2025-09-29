@echo off
REM Double-click to collect & analyze VTM logs (VTM 23.11) from your COARSE folder.
REM Edit ROOT if your path is different.

set ROOT=C:\Users\LQ Duy\Documents\Project\VideoCoding\VVCSoftware_VTM\analyze\runs_out_ablation\COARSE

python "%~dp0win_collect_and_analyze_v3.py" --root "%ROOT%" ^
  --out "%~dp0quickfire_summary_from_logs.csv" ^
  --overview "%~dp0quickfire_overview_from_logs.csv" ^
  --anchor-ref-name Baseline_Ref ^
  --anchor-min-name Baseline_Min ^
  --allow-2qp-estimate ^
  --fallback-perf-add-to-ref

echo.
echo Done. Outputs:
echo   %~dp0quickfire_summary_from_logs.csv
echo   %~dp0quickfire_overview_from_logs.csv
pause
