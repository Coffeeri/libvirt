{
  lib,
  runCommand,
  runtimeShell,
  python3,
  coreutils,
  iproute2,
  iputils,
  openssh,
  cloud-hypervisor-tdx,
  sshpass,
  test-helper,
  nixos-test-driver,
  testScriptFile,
  guestImage,
}:

let
  python = python3.withPackages (_: nixos-test-driver.dependencies ++ [ test-helper ]);
  drv =
    runCommand "tdx-bare-metal-test"
      {
        passthru.driver = drv;
        meta.mainProgram = "tdx-bare-metal-test";
      }
      ''
        mkdir -p $out/bin
        cat > $out/bin/tdx-bare-metal-test <<'EOF'
        #!${runtimeShell}
        set -euo pipefail

        export PATH="${
          lib.makeBinPath [
            coreutils
            iproute2
            iputils
            openssh
            sshpass
          ]
        }:''${PATH:-}"
        export TDX_CLOUD_HYPERVISOR="${cloud-hypervisor-tdx}/bin/cloud-hypervisor"

        if [[ -z "''${TDX_FIRMWARE:-}" ]]; then
          echo "TDX_FIRMWARE must point to an Intel TDX guest firmware image" >&2
          exit 2
        fi

        export TDX_IMAGE="''${TDX_IMAGE:-${guestImage}}"
        export PYTHONPATH="${python}/${python3.sitePackages}:${nixos-test-driver}/${python3.sitePackages}"
        exec ${python}/bin/python ${testScriptFile} "$@"
        EOF
        chmod +x $out/bin/tdx-bare-metal-test
      '';
in
drv
