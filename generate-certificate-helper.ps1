[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string] $PfxPath,
    [Parameter(Mandatory=$true)]
    [string] $Subject,
    [Parameter(Mandatory=$true)]
    [securestring] $Password
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$thumbprint = $null
try {
    $certificate = New-SelfSignedCertificate `
        -DNSName rcook.org `
        -Type CodeSigningCert `
        -Subject $Subject `
        -CertStoreLocation Cert:\CurrentUser\My
    $thumbprint = $certificate.Thumbprint
    $certificate | Export-PfxCertificate -FilePath $PfxPath -Password $Password | Out-Null
}
finally {
    if ($null -ne $thumbprint) {
        Remove-Item -Path Microsoft.PowerShell.Security\Certificate::CurrentUser\My\$thumbprint
    }
}
