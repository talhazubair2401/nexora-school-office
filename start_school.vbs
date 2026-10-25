' ======================================================================
'  Nexora School Office - office system launcher
'  Starts the system quietly in the background (if it isn't running yet)
'  and opens it in its own window. The desktop icon runs this file.
' ======================================================================
Option Explicit
Dim sh, fso, dir, url, i, browser, candidates, c

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
url = "http://127.0.0.1:8765/"

Function IsUp()
  Dim h
  IsUp = False
  On Error Resume Next
  Set h = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  h.setTimeouts 1000, 1000, 1000, 3000
  h.open "GET", url & "login/", False
  h.send
  If Err.Number = 0 Then
    If h.status = 200 Then IsUp = True
  End If
  Err.Clear
  On Error GoTo 0
End Function

If Not fso.FileExists(dir & "\venv\Scripts\python.exe") Then
  MsgBox "The system isn't installed yet." & vbCrLf & vbCrLf & _
         "Open the folder " & dir & " and double-click setup.bat first.", vbExclamation, "Nexora School Office"
  WScript.Quit 1
End If

If Not IsUp() Then
  sh.CurrentDirectory = dir
  ' Apply any updates to the database, then start the system hidden.
  sh.Run "cmd /c venv\Scripts\python.exe manage.py migrate --noinput > update_log.txt 2>&1", 0, True
  sh.Run "cmd /c venv\Scripts\python.exe manage.py runserver 127.0.0.1:8765 --noreload > server_log.txt 2>&1", 0, False
  For i = 1 To 60
    WScript.Sleep 500
    If IsUp() Then Exit For
  Next
  If Not IsUp() Then
    MsgBox "The system didn't start. Look at server_log.txt in " & dir & " for the reason.", vbCritical, "Nexora School Office"
    WScript.Quit 1
  End If
End If

' Open in its own app-style window (Edge, then Chrome), otherwise the normal browser.
candidates = Array( _
  sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe", _
  sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Microsoft\Edge\Application\msedge.exe", _
  sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Google\Chrome\Application\chrome.exe", _
  sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Google\Chrome\Application\chrome.exe", _
  sh.ExpandEnvironmentStrings("%LocalAppData%") & "\Google\Chrome\Application\chrome.exe")
browser = ""
For Each c In candidates
  If browser = "" And fso.FileExists(c) Then browser = c
Next

If browser <> "" Then
  sh.Run """" & browser & """ --app=" & url & " --window-size=1360,860", 1, False
Else
  sh.Run url, 1, False
End If
