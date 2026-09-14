#Requires -RunAsAdministrator
$n = 'VoiceATC-18650'
Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $n -Direction Inbound -Protocol TCP -LocalPort 18650 -Action Allow -Profile Any -Description 'ESP32 Flight Radar Voice ATC relay' | Out-Null
Write-Host "OK: inbound TCP 18650 allowed"
Get-NetFirewallRule -DisplayName $n | Format-List DisplayName, Enabled, Direction, Action, Profile
# Also ensure Docker Desktop related inbound isn't blocking
Get-NetFirewallProfile | Format-Table Name, Enabled, DefaultInboundAction -AutoSize
