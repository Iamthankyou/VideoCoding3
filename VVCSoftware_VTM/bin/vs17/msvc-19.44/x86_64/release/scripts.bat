@echo off
setlocal enabledelayedexpansion

set CFG_PATH="C:\Users\LQ Duy\Documents\Project\VideoCoding\VVCSoftware_VTM\cfg"
set INPUT_FILE="C:\Users\LQ Duy\Documents\Project\VideoCoding\Setup\BasketballPass_416x240_50.yuv"

set FRAMES_TO_ENCODE=33
set QP_VALUES=37 32 27 22

echo Starting VTM batch encoding test (33 frames per run)...
echo.

:: -----------------------------------------------------------------
:: ALL INTRA TESTS
:: -----------------------------------------------------------------
echo ##### RUNNING ALL-INTRA TESTS #####
set BASE_CFG=%CFG_PATH%\encoder_intra_vtm.cfg
set SEQ_CFG=%CFG_PATH%\per-sequence\BasketballPass.cfg

for %%q in (%QP_VALUES%) do (
    set QP=%%q
    echo.
    echo --- AI, QP=!QP! ---

    echo [AI-FULL] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% 2> log_AI_FULL_!QP!.txt

    echo [AI-Deblocking OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --DeblockingFilterDisable=1 2> log_AI_DEBLOCK_OFF_!QP!.txt

    echo [AI-SAO OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --SAO=0 2> log_AI_SAO_OFF_!QP!.txt

    echo [AI-TransformSkip OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --TransformSkip=0 2> log_AI_TS_OFF_!QP!.txt
)

:: -----------------------------------------------------------------
:: LOW DELAY B TESTS
:: -----------------------------------------------------------------
echo.
echo ##### RUNNING LOW-DELAY TESTS #####
set BASE_CFG=%CFG_PATH%\encoder_lowdelay_vtm.cfg

for %%q in (%QP_VALUES%) do (
    set QP=%%q
    echo.
    echo --- LDB, QP=!QP! ---

    echo [LDB-FULL] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% 2> log_LDB_FULL_!QP!.txt
    
    echo [LDB-FEN OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --FEN=0 2> log_LDB_FEN_OFF_!QP!.txt
    
    echo [LDB-FastSearch OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --FastSearch=0 2> log_LDB_FASTSEARCH_OFF_!QP!.txt
    
    echo [LDB-RDOQ OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --RDOQ=0 2> log_LDB_RDOQ_OFF_!QP!.txt
)

:: -----------------------------------------------------------------
:: RANDOM ACCESS TESTS
:: -----------------------------------------------------------------
echo.
echo ##### RUNNING RANDOM ACCESS TESTS #####
set BASE_CFG=%CFG_PATH%\encoder_randomaccess_vtm.cfg

for %%q in (%QP_VALUES%) do (
    set QP=%%q
    echo.
    echo --- RA, QP=!QP! ---

    echo [RA-FULL] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% 2> log_RA_FULL_!QP!.txt
    
    echo [RA-Deblocking OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --DeblockingFilterDisable=1 2> log_RA_DEBLOCK_OFF_!QP!.txt
    
    echo [RA-DMVR OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --DMVR=0 2> log_RA_DMVR_OFF_!QP!.txt

    echo [RA-TemporalFilter OFF] Running...
    EncoderApp.exe -c !BASE_CFG! -c !SEQ_CFG! -i %INPUT_FILE% -q !QP! -f %FRAMES_TO_ENCODE% --TemporalFilter=0 2> log_RA_TEMPORALFILTER_OFF_!QP!.txt
)

echo.
echo =================================================================
echo All VTM tests completed!
echo All log files have been saved (e.g., log_AI_FULL_37.txt).
echo Please check the SUMMARY section in each log file for results.
echo =================================================================

endlocal