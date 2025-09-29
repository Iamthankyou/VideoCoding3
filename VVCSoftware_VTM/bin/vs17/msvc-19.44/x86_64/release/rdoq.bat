@echo off
setlocal enabledelayedexpansion

:: =================================================================
:: PHẦN CÀI ĐẶT
:: =================================================================

set CFG_PATH=C:\Users\LQ Duy\Documents\Project\VideoCoding\VVCSoftware_VTM\cfg
set INPUT_FILE=C:\Users\LQ Duy\Documents\Project\VideoCoding\Setup\BasketballPass_416x240_50.yuv

set FRAMES_TO_ENCODE=33
set QP_VALUES=22

:: =================================================================
:: PHẦN THỰC THI
:: =================================================================

echo Starting VTM batch encoding test (33 frames per run)...
echo.

:: -----------------------------------------------------------------
:: BẢNG 2: LOW DELAY B TESTS
:: -----------------------------------------------------------------
echo.
echo ##### RUNNING LOW-DELAY TESTS #####
set BASE_CFG=%CFG_PATH%\encoder_lowdelay_vtm.cfg
set SEQ_CFG=%CFG_PATH%\per-sequence\BasketballPass.cfg

for %%q in (%QP_VALUES%) do (
    set QP=%%q
    echo.
    echo --- LDB, QP=!QP! ---

    echo [LDB-RDOQ OFF] Running...
    :: REM --- SỬA LỖI: Dùng "> file 2>&1" để ghi TẤT CẢ log ---
    EncoderApp.exe -c "!BASE_CFG!" -c "!SEQ_CFG!" -i "%INPUT_FILE%" -q !QP! -f %FRAMES_TO_ENCODE% --RDOQ=0 --DepQuant=0 > log_LDB_RDOQ_OFF1_!QP!.txt 2>&1
)

echo.
echo =================================================================
echo All VTM tests completed!
echo =================================================================

endlocal