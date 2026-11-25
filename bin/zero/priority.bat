@echo off >NUL
@SETLOCAL enableextensions enabledelayedexpansion
set "NetConID="
  wmic NIC where Description="ZeroTier Virtual Port" ^
    list /format:textvaluelist.xsl>"%temp%\wmcnc.txt" 2>&1
  for /F "tokens=1* delims==" %%I in ('type "%temp%\wmcnc.txt"') do (
    if /i "%%I"=="NetConnectionID" set "NetConID=%%~J"
  )
del "%temp%\wmcnc.txt" 2>nul
netsh interface ipv4 set interface "!NetConID!" metric=1