@echo off
cd /d D:\source\repos\KiCad-MCP-Server\projects\touch-panel
echo START %DATE% %TIME% > _fr_route2.log
"C:\Users\lixiaowei\.kicad-mcp\jdk25\jdk-25.0.4.1+1\bin\java.exe" -Xmx4g -jar "C:\Users\lixiaowei\.kicad-mcp\freerouting.jar" -de _fr.dsn -do _fr.ses -mp 50 -mt 15 -l en >> _fr_route2.log 2>&1
echo EXITCODE=%ERRORLEVEL% >> _fr_route2.log
echo DONE %DATE% %TIME% >> _fr_route2.log
