Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = oWS.SpecialFolders("Desktop") & "\JARVIS APEX Workstation.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)

' Path to Python and Desktop Launcher
oLink.TargetPath = "pythonw.exe"
oLink.Arguments = """" & oWS.CurrentDirectory & "\desktop_launcher.py"""
oLink.WorkingDirectory = oWS.CurrentDirectory
oLink.Description = "J.A.R.V.I.S. APEX Omni Intelligence Workstation"
oLink.WindowStyle = 1
oLink.Save

WScript.Echo "J.A.R.V.I.S. Desktop shortcut created successfully on your Desktop."
