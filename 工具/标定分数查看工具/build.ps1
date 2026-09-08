Set-Location -Path "D:\标定分数查看工具"

Write-Host "正在安装 PyInstaller..."
pip install pyinstaller -q

Write-Host "正在打包..."
pyinstaller --onefile --windowed --name "calibration_score" --collect-all "tkinter" main.py

if (Test-Path "dist\calibration_score.exe") {
    Write-Host "打包成功: dist\calibration_score.exe"
    Write-Host "文件大小: $((Get-Item 'dist\calibration_score.exe').Length / 1MB) MB"
} else {
    Write-Host "打包可能失败，请检查上方输出"
}

Read-Host "按 Enter 退出"