# Puts an "Nexora School Office" icon on the desktop that opens the system.
$folder  = $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$link    = Join-Path $desktop 'Nexora School Office.lnk'
$shell   = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath       = Join-Path $env:WINDIR 'System32\wscript.exe'
$s.Arguments        = '"' + (Join-Path $folder 'start_school.vbs') + '"'
$s.WorkingDirectory = $folder
$s.IconLocation     = (Join-Path $folder 'static\img\school.ico') + ',0'
$s.Description      = 'Nexora School Office - office records'
$s.Save()
Write-Output "Desktop icon created: $link"
