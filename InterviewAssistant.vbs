' ==============================================================================
'   Interview Assistant - Silent Windows Launcher (Zero Console / Zero Flashing)
'   Runs natively via Windows WScript (built into Win 7, 8, 10, 11)
' ==============================================================================

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get current application directory
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir

' 1. Locate Python executable (local runtime -> local python -> system python)
If fso.FileExists(strDir & "\runtime\python.exe") Then
    strPy = """" & strDir & "\runtime\python.exe"""
ElseIf fso.FileExists(strDir & "\python\python.exe") Then
    strPy = """" & strDir & "\python\python.exe"""
ElseIf fso.FileExists(strDir & "\.venv\Scripts\python.exe") Then
    strPy = """" & strDir & "\.venv\Scripts\python.exe"""
Else
    strPy = "python.exe"
End If

' 2. Pre-flight check: verify Python can execute on this Windows machine
intTest = WshShell.Run(strPy & " -c ""import sys""", 0, True)
If intTest <> 0 Then
    intAns = MsgBox("Interview Assistant could not launch the Python engine on your system." & vbCrLf & vbCrLf & _
             "If you are using Windows 7:" & vbCrLf & _
             "• Windows 7 requires the Microsoft Universal C Runtime (VC++ Redistributable)." & vbCrLf & _
             "• Windows 7 SP1 may also require Update KB2533623." & vbCrLf & _
             "• If your system is 32-bit, the 32-bit runtime must be downloaded." & vbCrLf & vbCrLf & _
             "Would you like to run the Windows 7 Compatibility Fixer now?", _
             vbYesNo + vbExclamation, "Interview Assistant - Windows 7 Compatibility Notice")
    If intAns = vbYes Then
        If fso.FileExists(strDir & "\fix_windows7.bat") Then
            WshShell.Run "cmd /c """ & strDir & "\fix_windows7.bat""", 1, False
        Else
            WshShell.Run "cmd /c """ & strDir & "\start_windows.bat""", 1, False
        End If
    End If
    WScript.Quit 1
End If

' 3. Terminate any previous engine instance holding port 9471 silently
WshShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon ^| findstr "":9471"" ^| findstr ""LISTENING""') do taskkill /F /PID %a 2>nul", 0, True

' 4. Launch Interview Assistant Engine completely hidden in background (0 = hidden)
WshShell.Run strPy & " """ & strDir & "\app.py""", 0, False

' 5. Wait 1.5 seconds for engine to bind port 9471
WScript.Sleep 1500

' 6. Open Interview Assistant HUD directly in default web browser
WshShell.Run "http://127.0.0.1:9471/", 1, False
